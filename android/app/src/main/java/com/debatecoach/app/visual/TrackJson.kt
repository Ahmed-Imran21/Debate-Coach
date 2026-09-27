package com.debatecoach.app.visual

/**
 * Serializes a VisualSignalTrack exactly as the website's
 * JSON.stringify(track) does: same key order (the order the web's
 * code builds each object in), same number formatting (JsMath.toJson),
 * no whitespace. VisualTrackParityTest compares the output byte for
 * byte against the web module's own output.
 */
object TrackJson {
    fun encode(track: VisualSignalTrack): String = buildString {
        obj {
            field("schema") { str(SCHEMA) }
            field("schema_version") { str(SCHEMA_VERSION) }
            field("session_id") { str(track.sessionId) }
            field("source") {
                val s = track.source
                obj {
                    field("platform") { str(s.platform) }
                    field("client_version") { str(s.clientVersion) }
                    field("user_agent_family") { str(s.userAgentFamily) }
                    field("runtime") {
                        obj {
                            field("name") { str(s.runtime.name) }
                            field("version") { str(s.runtime.version) }
                            field("delegate") { str(s.runtime.delegate) }
                        }
                    }
                    field("models") {
                        array(s.models) { m ->
                            obj {
                                field("task") { str(m.task) }
                                field("model_id") { str(m.modelId) }
                                field("sha256") { str(m.sha256) }
                            }
                        }
                    }
                    field("device_tier") { str(s.deviceTier) }
                    field("benchmark_fps") { num(s.benchmarkFps) }
                }
            }
            field("capture") {
                val c = track.capture
                obj {
                    field("frame_width") { num(c.frameWidth.toDouble()) }
                    field("frame_height") { num(c.frameHeight.toDouble()) }
                    field("input_mirrored") { bool(c.inputMirrored) }
                    field("handedness_convention") { str(c.handednessConvention) }
                    field("target_fps") { num(c.targetFps.toDouble()) }
                }
            }
            field("clock") {
                val c = track.clock
                obj {
                    field("t0_reference") { str(c.t0Reference) }
                    field("sync_method") { str(c.syncMethod) }
                    field("uncertainty_ms") { num(c.uncertaintyMs.toDouble()) }
                    field("duration_s") { num(c.durationS) }
                }
            }
            field("calibration") {
                val c = track.calibration
                obj {
                    field("performed") { bool(c.performed) }
                    field("baseline") {
                        val b = c.baseline
                        if (b == null) {
                            append("null")
                        } else {
                            obj {
                                field("head_yaw") { num(b.headYaw) }
                                field("head_pitch") { num(b.headPitch) }
                                field("iris_x") { num(b.irisX) }
                                field("iris_y") { num(b.irisY) }
                            }
                        }
                    }
                    field("samples") { num(c.samples.toDouble()) }
                    field("stability") { num(c.stability) }
                    field("right_hand_check") { str(c.rightHandCheck) }
                }
            }
            field("context") {
                obj {
                    field("setting") { str(track.context.setting) }
                    field("uses_notes") { bool(track.context.usesNotes) }
                }
            }
            field("setup_check") {
                val s = track.setupCheck
                obj {
                    field("face_visible") { bool(s.faceVisible) }
                    field("hands_visible_when_raised") { bool(s.handsVisibleWhenRaised) }
                    field("lighting") { str(s.lighting) }
                    field("distance") { str(s.distance) }
                }
            }
            field("frames") {
                obj {
                    field("t") { array(track.frames.t) { num(it) } }
                    FRAME_COLUMNS.forEachIndexed { i, name ->
                        field(name) { array(track.frames.columns[i]) { v -> if (v == null) append("null") else num(v) } }
                    }
                }
            }
            field("gaps") {
                array(track.gaps) { g ->
                    obj {
                        field("start") { num(g.start) }
                        field("end") { num(g.end) }
                        field("reason") { str(g.reason) }
                    }
                }
            }
            field("degradations") {
                array(track.degradations) { d ->
                    obj {
                        field("t") { num(d.t) }
                        field("face_fps") { num(d.faceFps.toDouble()) }
                        field("hands_fps") { num(d.handsFps.toDouble()) }
                        field("reason") { str(d.reason) }
                    }
                }
            }
        }
    }

    // --- a minimal writer that keeps insertion order ------------------

    private class ObjectScope(val sb: StringBuilder) {
        var first = true
        inline fun field(name: String, value: StringBuilder.() -> Unit) {
            if (!first) sb.append(',')
            first = false
            sb.str(name)
            sb.append(':')
            sb.value()
        }
    }

    private inline fun StringBuilder.obj(body: ObjectScope.() -> Unit) {
        append('{')
        ObjectScope(this).body()
        append('}')
    }

    private inline fun <T> StringBuilder.array(items: List<T>, item: StringBuilder.(T) -> Unit) {
        append('[')
        items.forEachIndexed { i, v ->
            if (i > 0) append(',')
            item(v)
        }
        append(']')
    }

    private fun StringBuilder.num(value: Double) {
        append(JsMath.toJson(value))
    }

    private fun StringBuilder.bool(value: Boolean) {
        append(if (value) "true" else "false")
    }

    /** JSON.stringify's string escaping. */
    fun StringBuilder.str(value: String) {
        append('"')
        for (ch in value) {
            when (ch) {
                '"' -> append("\\\"")
                '\\' -> append("\\\\")
                '\b' -> append("\\b")
                '\u000C' -> append("\\f")
                '\n' -> append("\\n")
                '\r' -> append("\\r")
                '\t' -> append("\\t")
                else -> if (ch < ' ' || ch.isSurrogate()) {
                    if (ch.isSurrogate()) append(ch) else append("\\u%04x".format(ch.code))
                } else {
                    append(ch)
                }
            }
        }
        append('"')
    }
}
