package com.debatecoach.app.visual.parity

import com.debatecoach.app.visual.AdaptiveScheduler
import com.debatecoach.app.visual.Benchmark
import com.debatecoach.app.visual.Calibration
import com.debatecoach.app.visual.CalibrationBaseline
import com.debatecoach.app.visual.Capture
import com.debatecoach.app.visual.TrackContext
import com.debatecoach.app.visual.Degradation
import com.debatecoach.app.visual.DetectedFace
import com.debatecoach.app.visual.DetectedHand
import com.debatecoach.app.visual.FRAME_COLUMNS
import com.debatecoach.app.visual.FrameDerivations
import com.debatecoach.app.visual.FrameResult
import com.debatecoach.app.visual.FrameSample
import com.debatecoach.app.visual.Framing
import com.debatecoach.app.visual.GazeCalibrationMath
import com.debatecoach.app.visual.Lighting
import com.debatecoach.app.visual.ModelInfo
import com.debatecoach.app.visual.Point2
import com.debatecoach.app.visual.RuntimeInfo
import com.debatecoach.app.visual.SetupCheck
import com.debatecoach.app.visual.Source
import com.debatecoach.app.visual.Stats
import com.debatecoach.app.visual.TrackBuilder
import com.debatecoach.app.visual.TrackJson
import com.debatecoach.app.visual.VisionMath
import com.debatecoach.app.visual.VisualConfig
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Web/Android parity for the visual signal extraction.
 *
 * Every case below comes from the website's own modules
 * (web/features/video-analysis), run by android/parity/generate-goldens.test.ts
 * on the inputs of the web's own tests (__tests__/math, stats, framing,
 * scheduler, track) plus thousands of seeded random and boundary inputs.
 * The Kotlin port must reproduce every output exactly: doubles bit for
 * bit, and built tracks byte for byte as JSON.
 */
class VisualParityGoldenTest {

    // ---------------------------------------------------------------
    // config.ts
    // ---------------------------------------------------------------

    @Test
    fun `every constant matches the web module`() {
        val golden = Goldens.load("config.json")
        val values = golden.obj("values")
        assertEquals("constant names", values.keys, VisualConfig.all.keys)
        for ((name, expected) in values) {
            val actual = VisualConfig.all.getValue(name)
            when {
                expected is JsonPrimitive && expected.booleanOrNull != null ->
                    assertEquals(name, expected.booleanOrNull, actual)
                expected is JsonPrimitive ->
                    assertSameDouble(expected.num(), (actual as Number).toDouble(), name)
                else ->
                    assertEquals(name, expected.nums(), (actual as List<*>).map { (it as Number).toDouble() })
            }
        }
        val models = golden.obj("manifest").arr("models").map {
            val o = it.jsonObject
            ModelInfo(o.getValue("task").str(), o.getValue("model_id").str(), o.getValue("sha256").str())
        }
        assertEquals("the same MediaPipe model files", models, VisualConfig.MODELS)
    }

    // ---------------------------------------------------------------
    // math.ts
    // ---------------------------------------------------------------

    @Test
    fun `head pose matches for every matrix`() {
        val cases = Goldens.load("math.json").arr("headPose")
        assertTrue(cases.size > 400)
        cases.mapIndexedCases { i, c ->
            val pose = VisionMath.headPoseFromMatrix(c.getValue("matrix").nums(), c.getValue("columns").int())
            val out = c.obj("out")
            assertSameDouble(out.getValue("yaw").num(), pose.yaw, "headPose[$i].yaw")
            assertSameDouble(out.getValue("pitch").num(), pose.pitch, "headPose[$i].pitch")
            assertSameDouble(out.getValue("roll").num(), pose.roll, "headPose[$i].roll")
        }
    }

    @Test
    fun `iris offset matches, including blinks and missing landmarks`() {
        val cases = Goldens.load("math.json").arr("iris")
        var nulls = 0
        cases.mapIndexedCases { i, c ->
            val out = VisionMath.computeIrisOffset(c.getValue("landmarks").landmarks(), c.getValue("width").num(), c.getValue("height").num())
            val expected = c.getValue("out")
            if (expected is JsonNull) {
                nulls++
                assertNull("iris[$i]", out)
            } else {
                val e = expected.jsonObject
                assertSameDouble(e.getValue("x").num(), out!!.x, "iris[$i].x")
                assertSameDouble(e.getValue("y").num(), out.y, "iris[$i].y")
            }
        }
        assertTrue("some blinks/missing cases are covered", nulls >= 3)
    }

    @Test
    fun `face scale and center match`() {
        val math = Goldens.load("math.json")
        math.arr("faceScale").mapIndexedCases { i, c ->
            val out = VisionMath.computeFaceScale(c.getValue("landmarks").landmarks(), c.getValue("width").num())
            assertSameDouble(c["out"].numOrNull(), out, "faceScale[$i]")
        }
        math.arr("faceCenter").mapIndexedCases { i, c ->
            val out = VisionMath.computeFaceCenter(c.getValue("landmarks").landmarks())
            val expected = c.getValue("out")
            if (expected is JsonNull) {
                assertNull("faceCenter[$i]", out)
            } else {
                assertSameDouble(expected.jsonObject.getValue("cx").num(), out!!.cx, "faceCenter[$i].cx")
                assertSameDouble(expected.jsonObject.getValue("cy").num(), out.cy, "faceCenter[$i].cy")
            }
        }
    }

    @Test
    fun `primary face selection matches`() {
        Goldens.load("math.json").arr("primary").mapIndexedCases { i, c ->
            val faces = c.arr("faces").map {
                val f = it.jsonObject
                val center = f.obj("center")
                VisionMath.FaceCandidate(Point2(center.getValue("cx").num(), center.getValue("cy").num()), f.getValue("scale").num())
            }
            val baseline = c["baseline"]?.takeIf { it !is JsonNull }?.jsonObject?.let { Point2(it.getValue("cx").num(), it.getValue("cy").num()) }
            assertEquals("primary[$i]", c.getValue("out").int(), VisionMath.selectPrimaryFace(faces, baseline))
        }
    }

    @Test
    fun `hand centroids and sides match`() {
        val math = Goldens.load("math.json")
        math.arr("palm").mapIndexedCases { i, c ->
            val out = VisionMath.computePalmCentroid(c.getValue("landmarks").landmarks())
            val expected = c.getValue("out")
            if (expected is JsonNull) {
                assertNull("palm[$i]", out)
            } else {
                assertSameDouble(expected.jsonObject.getValue("cx").num(), out!!.cx, "palm[$i].cx")
                assertSameDouble(expected.jsonObject.getValue("cy").num(), out.cy, "palm[$i].cy")
            }
        }
        math.arr("twoHands").mapIndexedCases { i, c ->
            val cx = c.getValue("cx").nums()
            val (rh, lh) = VisionMath.assignTwoHandSides(cx[0], cx[1])
            assertEquals("twoHands[$i].rh", c.getValue("rh").int(), rh)
            assertEquals("twoHands[$i].lh", c.getValue("lh").int(), lh)
        }
        math.arr("handLabel").mapIndexedCases { i, c ->
            val out = VisionMath.resolveHandSideFromLabel(c.getValue("label").str(), c.getValue("inverted").jsonPrimitive.booleanOrNull!!)
            assertEquals("handLabel[$i]", c.getValue("out").str(), out.wire)
        }
    }

    // ---------------------------------------------------------------
    // stats.ts and framing.ts
    // ---------------------------------------------------------------

    @Test
    fun `stats match, including empty lists and signed zeros`() {
        val stats = Goldens.load("stats.json")
        stats.arr("percentile90").mapIndexedCases { i, c ->
            assertSameDouble(c.getValue("out").num(), Stats.percentile90(c.getValue("values").nums()), "percentile90[$i]")
        }
        stats.arr("median").mapIndexedCases { i, c ->
            assertSameDouble(c.getValue("out").num(), Stats.median(c.getValue("values").nums()), "median[$i]")
        }
        stats.arr("meanAbsoluteDeviation").mapIndexedCases { i, c ->
            val out = Stats.meanAbsoluteDeviation(c.getValue("values").nums(), c.getValue("center").num())
            assertSameDouble(c.getValue("out").num(), out, "mad[$i]")
        }
        stats.arr("clamp").mapIndexedCases { i, c ->
            val out = Stats.clamp(c.getValue("v").num(), c.getValue("lo").num(), c.getValue("hi").num())
            assertSameDouble(c.getValue("out").num(), out, "clamp[$i]")
        }
    }

    @Test
    fun `framing checks match`() {
        val framing = Goldens.load("framing.json")
        framing.arr("ratioTrue").mapIndexedCases { i, c ->
            assertSameDouble(c.getValue("out").num(), Framing.ratioTrue(c.getValue("flags").bools()), "ratioTrue[$i]")
        }
        framing.arr("faceVisible").mapIndexedCases { i, c ->
            assertEquals("faceVisible[$i]", c.getValue("out").jsonPrimitive.booleanOrNull, Framing.faceVisiblePasses(c.getValue("flags").bools()))
        }
        framing.arr("handsRaised").mapIndexedCases { i, c ->
            assertEquals("handsRaised[$i]", c.getValue("out").jsonPrimitive.booleanOrNull, Framing.handsRaisedPasses(c.getValue("flags").bools()))
        }
        framing.arr("distance").mapIndexedCases { i, c ->
            assertEquals("distance[$i]", c.getValue("out").str(), Framing.classifyDistance(c.getValue("scales").nums()))
        }
        framing.arr("lighting").mapIndexedCases { i, c ->
            assertEquals("lighting[$i]", c.getValue("out").str(), Framing.classifyLighting(c.getValue("mean").num(), c["face"].numOrNull()))
        }
    }

    // ---------------------------------------------------------------
    // scheduler.ts: replay every recorded call sequence
    // ---------------------------------------------------------------

    @Test
    fun `the adaptive scheduler replays every sequence identically`() {
        val scenarios = Goldens.load("scheduler.json").arr("scenarios")
        assertTrue(scenarios.size >= 70)
        var degradations = 0
        scenarios.mapIndexedCases { s, scenario ->
            val name = scenario.getValue("name").str()
            val scheduler = AdaptiveScheduler()
            scenario.arr("ops").mapIndexedCases { i, op ->
                val where = "$name op $i"
                when (op.getValue("op").str()) {
                    "shouldTick" -> assertEquals(where, op.getValue("out").jsonPrimitive.booleanOrNull, scheduler.shouldTick(op.getValue("now").num()))
                    "planHands" -> assertEquals(where, op.getValue("out").jsonPrimitive.booleanOrNull, scheduler.planHands())
                    "recordTick" -> {
                        val out = scheduler.recordTick(op.getValue("now").num(), op.getValue("inferMs").num(), op.getValue("handsRan").jsonPrimitive.booleanOrNull!!)
                        val expected = op.getValue("out")
                        if (expected is JsonNull) {
                            assertNull(where, out)
                        } else {
                            degradations++
                            assertDegradation(expected.jsonObject, out, where)
                        }
                    }
                    "state" -> {
                        val e = op.obj("out")
                        assertEquals("$where mode", e.getValue("mode").str(), scheduler.currentHandsMode.wire)
                        assertEquals("$where disabled", e.getValue("disabled").jsonPrimitive.booleanOrNull, scheduler.isDisabled)
                        assertEquals("$where fps", e.getValue("fps").int(), scheduler.currentEffectiveFps)
                    }
                }
            }
            s
        }
        assertTrue("degradations are exercised", degradations > 10)
    }

    private fun assertDegradation(expected: JsonObject, actual: Degradation?, where: String) {
        requireNotNull(actual) { "$where: expected a degradation, got none" }
        assertSameDouble(expected.getValue("t").num(), actual.t, "$where t")
        assertEquals("$where face_fps", expected.getValue("face_fps").int(), actual.faceFps)
        assertEquals("$where hands_fps", expected.getValue("hands_fps").int(), actual.handsFps)
        assertEquals("$where reason", expected.getValue("reason").str(), actual.reason)
    }

    // ---------------------------------------------------------------
    // track.ts: the serialized track, byte for byte
    // ---------------------------------------------------------------

    @Test
    fun `built tracks serialize byte for byte like the web`() {
        val scenarios = Goldens.load("track.json").arr("scenarios")
        assertTrue(scenarios.size >= 50)
        scenarios.mapIndexedCases { _, scenario ->
            val name = scenario.getValue("name").str()
            val builder = TrackBuilder()
            scenario.arr("ops").mapIndexedCases { i, op ->
                val where = "$name op $i"
                when (op.getValue("op").str()) {
                    "append" -> assertEquals(where, op.getValue("out").jsonPrimitive.booleanOrNull, builder.appendSample(op.getValue("t").num(), sample(op.obj("sample"))))
                    "appendEmpty" -> assertEquals(where, op.getValue("out").jsonPrimitive.booleanOrNull, builder.appendEmpty(op.getValue("t").num()))
                    "openGap" -> builder.openGapAt(op.getValue("t").num(), op.getValue("reason").str())
                    "closeGap" -> builder.closeGapAt(op.getValue("t").num())
                    "degradation" -> {
                        val d = op.obj("value")
                        builder.pushDegradation(Degradation(d.getValue("t").num(), d.getValue("face_fps").int(), d.getValue("hands_fps").int(), d.getValue("reason").str()))
                    }
                    "state" -> {
                        val e = op.obj("out")
                        assertEquals("$where frameCount", e.getValue("frameCount").int(), builder.frameCount)
                        assertEquals("$where hasOpenGap", e.getValue("hasOpenGap").jsonPrimitive.booleanOrNull, builder.hasOpenGap)
                        assertSameDouble(e["lastT"].numOrNull(), builder.lastAppendedT, "$where lastT")
                    }
                }
            }
            val p = scenario.obj("params")
            val track = builder.build(
                sessionId = p.getValue("sessionId").str(),
                source = source(p.obj("source")),
                capture = capture(p.obj("capture")),
                clockUncertaintyMs = p.getValue("clockUncertaintyMs").int(),
                durationS = p.getValue("durationS").num(),
                calibration = calibration(p.obj("calibration")),
                context = p.obj("context").let { TrackContext(it.getValue("setting").str(), it.getValue("uses_notes").jsonPrimitive.booleanOrNull!!) },
                setupCheck = p.obj("setupCheck").let {
                    SetupCheck(it.getValue("face_visible").jsonPrimitive.booleanOrNull!!, it.getValue("hands_visible_when_raised").jsonPrimitive.booleanOrNull!!, it.getValue("lighting").str(), it.getValue("distance").str())
                },
            )
            assertEquals("$name: JSON.stringify(track)", scenario.getValue("json").str(), TrackJson.encode(track))
        }
    }

    private fun sample(o: JsonObject): FrameSample = FrameSample.fromColumns(FRAME_COLUMNS.map { o[it].numOrNull() })

    private fun source(o: JsonObject): Source {
        val r = o.obj("runtime")
        return Source(
            platform = o.getValue("platform").str(),
            clientVersion = o.getValue("client_version").str(),
            userAgentFamily = o.getValue("user_agent_family").str(),
            runtime = RuntimeInfo(r.getValue("name").str(), r.getValue("version").str(), r.getValue("delegate").str()),
            models = o.arr("models").map { m ->
                val mo = m.jsonObject
                ModelInfo(mo.getValue("task").str(), mo.getValue("model_id").str(), mo.getValue("sha256").str())
            },
            deviceTier = o.getValue("device_tier").str(),
            benchmarkFps = o.getValue("benchmark_fps").num(),
        )
    }

    private fun capture(o: JsonObject) = Capture(
        o.getValue("frame_width").int(),
        o.getValue("frame_height").int(),
        o.getValue("input_mirrored").jsonPrimitive.booleanOrNull!!,
        o.getValue("handedness_convention").str(),
        o.getValue("target_fps").int(),
    )

    private fun calibration(o: JsonObject) = Calibration(
        performed = o.getValue("performed").jsonPrimitive.booleanOrNull!!,
        baseline = o["baseline"]?.takeIf { it !is JsonNull }?.jsonObject?.let {
            CalibrationBaseline(it.getValue("head_yaw").num(), it.getValue("head_pitch").num(), it.getValue("iris_x").num(), it.getValue("iris_y").num())
        },
        samples = o.getValue("samples").int(),
        stability = o.getValue("stability").num(),
        rightHandCheck = o.getValue("right_hand_check").str(),
    )

    // ---------------------------------------------------------------
    // useVisualCapture.ts glue: per-frame derivation, tiers,
    // calibration, lighting
    // ---------------------------------------------------------------

    @Test
    fun `each frame derives the same sample as the web's processTick`() {
        val frames = Goldens.load("composition.json").arr("frames")
        assertTrue(frames.size >= 400)
        frames.mapIndexedCases { i, c ->
            val result = FrameResult(
                faces = c.arr("faces").map { f ->
                    val fo = f.jsonObject
                    DetectedFace(fo.getValue("landmarks").landmarks(), fo["transformMatrix"]?.takeIf { it !is JsonNull }?.nums())
                },
                hands = c.arr("hands").map { h ->
                    val ho = h.jsonObject
                    DetectedHand(ho.getValue("landmarks").landmarks(), ho.getValue("handednessLabel").str(), ho.getValue("handednessScore").num())
                },
            )
            val baseline = c["baseline"]?.takeIf { it !is JsonNull }?.jsonObject?.let { Point2(it.getValue("cx").num(), it.getValue("cy").num()) }
            val d = FrameDerivations.derive(
                result,
                baseline,
                c.getValue("inverted").jsonPrimitive.booleanOrNull!!,
                c.getValue("runHands").jsonPrimitive.booleanOrNull!!,
                c.getValue("inferMs").num(),
            )
            val out = c.obj("out")
            val expected = out.obj("sample")
            val actual = d.sample.columns()
            FRAME_COLUMNS.forEachIndexed { k, column -> assertSameDouble(expected[column].numOrNull(), actual[k], "frame[$i].$column") }
            assertEquals("frame[$i] both hands", out.getValue("bothHands").jsonPrimitive.booleanOrNull, d.lh != null && d.rh != null)
            assertEquals("frame[$i] right hand", out.getValue("rightHand").jsonPrimitive.booleanOrNull, d.rh != null)
        }
    }

    @Test
    fun `device tiers match the web's benchmark`() {
        Goldens.load("composition.json").arr("tiers").mapIndexedCases { i, c ->
            val result = Benchmark.decide(c.getValue("ticks").int(), c.getValue("latencies").nums())
            assertEquals("tier[$i]", c.getValue("tier").str(), result.tier)
            assertSameDouble(c.getValue("benchmarkFps").num(), result.benchmarkFps, "tier[$i].benchmarkFps")
        }
    }

    @Test
    fun `calibration matches`() {
        val composition = Goldens.load("composition.json")
        composition.arr("calibrations").mapIndexedCases { i, c ->
            val result = GazeCalibrationMath.compute(
                c.getValue("yaw").nums(), c.getValue("pitch").nums(), c.getValue("irisX").nums(), c.getValue("irisY").nums(),
                c.getValue("cx").nums(), c.getValue("cy").nums(),
            )
            val out = c.obj("out")
            assertEquals("calibration[$i].performed", out.getValue("performed").jsonPrimitive.booleanOrNull, result.performed)
            assertEquals("calibration[$i].samples", out.getValue("samples").int(), result.samples)
            if (result.performed) {
                val b = out.obj("baseline")
                assertSameDouble(b.getValue("head_yaw").num(), result.baseline!!.headYaw, "calibration[$i].head_yaw")
                assertSameDouble(b.getValue("head_pitch").num(), result.baseline.headPitch, "calibration[$i].head_pitch")
                assertSameDouble(b.getValue("iris_x").num(), result.baseline.irisX, "calibration[$i].iris_x")
                assertSameDouble(b.getValue("iris_y").num(), result.baseline.irisY, "calibration[$i].iris_y")
                assertSameDouble(out.getValue("stability").num(), result.stability, "calibration[$i].stability")
                val center = out.getValue("faceCenter")
                if (center is JsonNull) assertNull(result.faceCenter) else {
                    assertSameDouble(center.jsonObject.getValue("cx").num(), result.faceCenter!!.cx, "calibration[$i].cx")
                    assertSameDouble(center.jsonObject.getValue("cy").num(), result.faceCenter.cy, "calibration[$i].cy")
                }
            }
        }
        composition.arr("rightHand").mapIndexedCases { i, c ->
            assertEquals("rightHand[$i]", c.getValue("out").str(), GazeCalibrationMath.rightHandCheck(c.getValue("flags").bools()))
        }
    }

    @Test
    fun `lighting luma matches the web's canvas sampling`() {
        Goldens.load("composition.json").arr("lighting").mapIndexedCases { i, c ->
            val rgba = c.getValue("rgba").jsonArray.map { it.int() }.toIntArray()
            val luma = Lighting.measure(c.getValue("width").int(), c.getValue("height").int(), rgba)
            assertSameDouble(c.getValue("meanLuma").num(), luma.meanLuma, "lighting[$i].mean")
            assertSameDouble(c["faceLuma"].numOrNull(), luma.faceLuma, "lighting[$i].face")
            assertEquals("lighting[$i]", c.getValue("out").str(), Framing.classifyLighting(luma.meanLuma, luma.faceLuma))
        }
    }
}
