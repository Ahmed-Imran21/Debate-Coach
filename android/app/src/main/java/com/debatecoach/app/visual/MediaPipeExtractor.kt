package com.debatecoach.app.visual

import android.content.Context
import android.graphics.Bitmap
import com.debatecoach.app.BuildConfig
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.core.Delegate
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarker
import com.google.mediapipe.tasks.vision.handlandmarker.HandLandmarker

/**
 * The Android counterpart of web/features/video-analysis/extractor.ts.
 * Deliberately dumb: it only calls MediaPipe and hands back raw
 * landmarks and matrices; every derived number is computed by the
 * ported pure functions (VisionMath, FrameDerivations).
 *
 * Same models (the website's exact .task files, bundled from
 * assets/mediapipe/), same options (VIDEO mode, 2 faces with
 * transformation matrices, 2 hands), same GPU-then-CPU fallback.
 * No image ever leaves this class: frames are processed and dropped.
 */
class MediaPipeExtractor private constructor(
    private val face: FaceLandmarker,
    private val hands: HandLandmarker,
    val delegate: String,
) {
    private var lastTimestampMs = -1L

    /** detectForVideo on both models. `timestampMs` must increase; equal values are nudged. */
    fun process(bitmap: Bitmap, timestampMs: Double, runHands: Boolean): FrameResult {
        val ts = maxOf(lastTimestampMs + 1, timestampMs.toLong())
        lastTimestampMs = ts
        val image = BitmapImageBuilder(bitmap).build()
        try {
            val faceResult = face.detectForVideo(image, ts)
            val matrices = faceResult.facialTransformationMatrixes().orElse(null)
            val faces = faceResult.faceLandmarks().mapIndexed { index, landmarks ->
                DetectedFace(
                    landmarks = landmarks.map { Landmark(it.x().toDouble(), it.y().toDouble(), it.z().toDouble()) },
                    transformMatrix = matrices?.getOrNull(index)?.map { it.toDouble() },
                )
            }
            val detectedHands = if (runHands) {
                val handResult = hands.detectForVideo(image, ts)
                val handedness = handResult.handedness()
                handResult.landmarks().mapIndexed { index, landmarks ->
                    val category = handedness.getOrNull(index)?.firstOrNull()
                    DetectedHand(
                        landmarks = landmarks.map { Landmark(it.x().toDouble(), it.y().toDouble(), it.z().toDouble()) },
                        handednessLabel = category?.categoryName() ?: "Right",
                        handednessScore = category?.score()?.toDouble() ?: 0.0,
                    )
                }
            } else {
                emptyList()
            }
            return FrameResult(faces, detectedHands)
        } finally {
            image.close()
        }
    }

    fun close() {
        runCatching { face.close() }
        runCatching { hands.close() }
    }

    companion object {
        const val RUNTIME_NAME = "mediapipe-tasks-vision"
        val runtimeVersion: String get() = BuildConfig.MEDIAPIPE_VERSION

        /** GPU first, then CPU, as on the web. Throws if neither loads (model_load_failed). */
        fun create(context: Context): MediaPipeExtractor {
            var lastError: Throwable? = null
            for (delegate in listOf(Delegate.GPU, Delegate.CPU)) {
                var face: FaceLandmarker? = null
                try {
                    face = FaceLandmarker.createFromOptions(
                        context,
                        FaceLandmarker.FaceLandmarkerOptions.builder()
                            .setBaseOptions(base("mediapipe/face_landmarker.task", delegate))
                            .setRunningMode(RunningMode.VIDEO)
                            .setNumFaces(2)
                            .setOutputFaceBlendshapes(false)
                            .setOutputFacialTransformationMatrixes(true)
                            .build(),
                    )
                    val hands = HandLandmarker.createFromOptions(
                        context,
                        HandLandmarker.HandLandmarkerOptions.builder()
                            .setBaseOptions(base("mediapipe/hand_landmarker.task", delegate))
                            .setRunningMode(RunningMode.VIDEO)
                            .setNumHands(2)
                            .build(),
                    )
                    return MediaPipeExtractor(face, hands, if (delegate == Delegate.GPU) "GPU" else "CPU")
                } catch (error: Throwable) {
                    runCatching { face?.close() }
                    lastError = error
                }
            }
            throw IllegalStateException("model_load_failed", lastError)
        }

        private fun base(path: String, delegate: Delegate): BaseOptions =
            BaseOptions.builder().setModelAssetPath(path).setDelegate(delegate).build()
    }
}
