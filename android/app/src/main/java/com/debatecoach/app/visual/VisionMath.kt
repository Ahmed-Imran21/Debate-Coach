package com.debatecoach.app.visual

/*
 * web/features/video-analysis/math.ts, line for line: head pose, iris
 * offset, face scale and center, primary face, palm centroid and hand
 * sides. Pure functions of plain numbers, so the golden test can feed
 * them the web's exact inputs. Arithmetic is kept in the web's order.
 *
 * The same sign/layout caveat as the web applies (math.ts header): the
 * *_SIGN constants and the column-major assumption must be confirmed
 * on a real camera. They are shared, so the two platforms agree.
 */

data class Landmark(val x: Double, val y: Double, val z: Double = 0.0)

data class HeadPose(val yaw: Double, val pitch: Double, val roll: Double)

data class IrisOffset(val x: Double, val y: Double)

data class Point2(val cx: Double, val cy: Double)

enum class HandSide(val wire: String) { LH("lh"), RH("rh") }

object VisionMath {
    private const val MATRIX_IS_COLUMN_MAJOR = true

    const val YAW_SIGN = 1.0
    const val PITCH_SIGN = 1.0
    const val ROLL_SIGN = 1.0

    private const val RAD_TO_DEG = 180 / Math.PI

    /** Top-left 3x3 rotation block of a flattened matrix, as [row][col]. */
    fun rotationFromMatrix(data: List<Double>, columns: Int = 4): Array<DoubleArray> {
        fun at(row: Int, col: Int): Double =
            if (MATRIX_IS_COLUMN_MAJOR) data.getOrElse(col * columns + row) { Double.NaN } else data.getOrElse(row * columns + col) { Double.NaN }
        return arrayOf(
            doubleArrayOf(at(0, 0), at(0, 1), at(0, 2)),
            doubleArrayOf(at(1, 0), at(1, 1), at(1, 2)),
            doubleArrayOf(at(2, 0), at(2, 1), at(2, 2)),
        )
    }

    /** R = Ry(yaw) · Rx(pitch) · Rz(roll), degrees, unrounded. */
    fun headPoseFromRotation(r: Array<DoubleArray>): HeadPose {
        val pitchRad = JsMath.asin(clamp(-r[1][2], -1.0, 1.0))
        val yawRad = JsMath.atan2(r[0][2], r[2][2])
        val rollRad = JsMath.atan2(r[1][0], r[1][1])
        return HeadPose(
            yaw = YAW_SIGN * yawRad * RAD_TO_DEG,
            pitch = PITCH_SIGN * pitchRad * RAD_TO_DEG,
            roll = ROLL_SIGN * rollRad * RAD_TO_DEG,
        )
    }

    fun headPoseFromMatrix(data: List<Double>, columns: Int = 4): HeadPose =
        headPoseFromRotation(rotationFromMatrix(data, columns))

    private fun clamp(value: Double, lo: Double, hi: Double): Double = JsMath.min(hi, JsMath.max(lo, value))

    // -----------------------------------------------------------
    // Iris offset
    // -----------------------------------------------------------

    private data class Eye(val outer: Int, val inner: Int, val upper: Int, val lower: Int, val iris: Int)

    private val LEFT_EYE = Eye(outer = 33, inner = 133, upper = 159, lower = 145, iris = 468)
    private val RIGHT_EYE = Eye(outer = 263, inner = 362, upper = 386, lower = 374, iris = 473)

    private const val MIN_EYE_HEIGHT_PX = 2.0
    private const val IRIS_CLAMP = 1.5

    private class EyeRaw(val rawX: Double, val rawY: Double, val heightPx: Double)

    private fun eyeOffset(landmarks: List<Landmark?>, eye: Eye, frameWidth: Double, frameHeight: Double): EyeRaw? {
        val outer = landmarks.getOrNull(eye.outer) ?: return null
        val inner = landmarks.getOrNull(eye.inner) ?: return null
        val upper = landmarks.getOrNull(eye.upper) ?: return null
        val lower = landmarks.getOrNull(eye.lower) ?: return null
        val iris = landmarks.getOrNull(eye.iris) ?: return null

        val outerX = outer.x * frameWidth
        val innerX = inner.x * frameWidth
        val upperY = upper.y * frameHeight
        val lowerY = lower.y * frameHeight
        val irisX = iris.x * frameWidth
        val irisY = iris.y * frameHeight

        val cx = (outerX + innerX) / 2
        val halfW = kotlin.math.abs(outerX - innerX) / 2
        val cy = (upperY + lowerY) / 2
        val heightPx = kotlin.math.abs(upperY - lowerY)
        val halfH = JsMath.max(heightPx / 2, 1e-6)

        return EyeRaw(
            rawX = (irisX - cx) / JsMath.max(halfW, 1e-6),
            rawY = (irisY - cy) / halfH,
            heightPx = heightPx,
        )
    }

    /**
     * Averaged, sign-corrected iris offset in [-1.5, 1.5], or null on a
     * blink. +x: the speaker looks toward their own right. +y: up.
     */
    fun computeIrisOffset(landmarks: List<Landmark?>, frameWidth: Double, frameHeight: Double): IrisOffset? {
        val left = eyeOffset(landmarks, LEFT_EYE, frameWidth, frameHeight) ?: return null
        val right = eyeOffset(landmarks, RIGHT_EYE, frameWidth, frameHeight) ?: return null
        if (left.heightPx < MIN_EYE_HEIGHT_PX || right.heightPx < MIN_EYE_HEIGHT_PX) return null

        val rawX = (left.rawX + right.rawX) / 2
        val rawY = (left.rawY + right.rawY) / 2
        return IrisOffset(
            x = clamp(-rawX, -IRIS_CLAMP, IRIS_CLAMP),
            y = clamp(-rawY, -IRIS_CLAMP, IRIS_CLAMP),
        )
    }

    // -----------------------------------------------------------
    // Face scale and center
    // -----------------------------------------------------------

    private const val FACE_SCALE_LEFT = 33
    private const val FACE_SCALE_RIGHT = 263

    /** Outer-eye-corner distance in pixels, divided by frame width. */
    fun computeFaceScale(landmarks: List<Landmark?>, frameWidth: Double): Double? {
        val a = landmarks.getOrNull(FACE_SCALE_LEFT) ?: return null
        val b = landmarks.getOrNull(FACE_SCALE_RIGHT) ?: return null
        val dx = (a.x - b.x) * frameWidth
        val dy = (a.y - b.y) * frameWidth
        return JsMath.hypot(dx, dy) / frameWidth
    }

    /** Mean of every landmark's normalized x/y. */
    fun computeFaceCenter(landmarks: List<Landmark?>): Point2? {
        if (landmarks.isEmpty()) return null
        var sx = 0.0
        var sy = 0.0
        for (lm in landmarks) {
            // A hole (undefined in JS) makes the web's sum NaN; mirror it.
            sx += lm?.x ?: Double.NaN
            sy += lm?.y ?: Double.NaN
        }
        return Point2(sx / landmarks.size, sy / landmarks.size)
    }

    data class FaceCandidate(val center: Point2, val scale: Double)

    /** Closest to the calibration baseline, else the largest; first wins ties. */
    fun selectPrimaryFace(faces: List<FaceCandidate>, baseline: Point2?): Int {
        if (faces.size <= 1) return 0
        if (baseline != null) {
            var best = 0
            var bestDist = Double.POSITIVE_INFINITY
            faces.forEachIndexed { index, face ->
                val dist = JsMath.hypot(face.center.cx - baseline.cx, face.center.cy - baseline.cy)
                if (dist < bestDist) {
                    bestDist = dist
                    best = index
                }
            }
            return best
        }
        var best = 0
        faces.forEachIndexed { index, face ->
            if (face.scale > faces[best].scale) best = index
        }
        return best
    }

    // -----------------------------------------------------------
    // Hands
    // -----------------------------------------------------------

    private val PALM_LANDMARKS = intArrayOf(0, 5, 9, 13, 17)

    fun computePalmCentroid(landmarks: List<Landmark?>): Point2? {
        var sx = 0.0
        var sy = 0.0
        var n = 0
        for (index in PALM_LANDMARKS) {
            val lm = landmarks.getOrNull(index) ?: return null
            sx += lm.x
            sy += lm.y
            n += 1
        }
        return Point2(sx / n, sy / n)
    }

    /** Two hands: the smaller-cx one is the speaker's right hand (unmirrored frame). Returns (rhIndex, lhIndex). */
    fun assignTwoHandSides(cx0: Double, cx1: Double): Pair<Int, Int> = if (cx0 <= cx1) 0 to 1 else 1 to 0

    /** One hand: MediaPipe's label, inverted by default (it assumes a mirrored selfie). */
    fun resolveHandSideFromLabel(label: String, inverted: Boolean): HandSide {
        val isRight = if (inverted) label == "Left" else label == "Right"
        return if (isRight) HandSide.RH else HandSide.LH
    }
}
