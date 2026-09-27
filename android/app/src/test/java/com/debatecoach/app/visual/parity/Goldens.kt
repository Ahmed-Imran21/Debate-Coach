package com.debatecoach.app.visual.parity

import com.debatecoach.app.visual.Landmark
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.double
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.fail

/**
 * Reads the golden vectors written by android/parity/generate-goldens.test.ts
 * (the website's own modules, run on the website's own test inputs plus
 * seeded random ones).
 */
object Goldens {
    fun load(name: String): JsonObject {
        val text = Goldens::class.java.classLoader!!.getResourceAsStream("parity/$name")
            ?.bufferedReader()?.readText()
            ?: error("Missing golden parity/$name. Run android/parity/check-goldens.sh.")
        return Json.parseToJsonElement(text).jsonObject
    }
}

/** A number as the generator encoded it: plain, or "NaN" / "Infinity" / "-Infinity" / "-0". */
fun JsonElement.num(): Double {
    val p = jsonPrimitive
    if (p.isString) {
        return when (p.content) {
            "NaN" -> Double.NaN
            "Infinity" -> Double.POSITIVE_INFINITY
            "-Infinity" -> Double.NEGATIVE_INFINITY
            "-0" -> -0.0
            else -> error("Unexpected encoded number ${p.content}")
        }
    }
    return p.double
}

fun JsonElement?.numOrNull(): Double? = if (this == null || this is JsonNull) null else num()

fun JsonElement.nums(): List<Double> = jsonArray.map { it.num() }

fun JsonElement.bools(): List<Boolean> = jsonArray.map { it.jsonPrimitive.booleanOrNull!! }

fun JsonElement.str(): String = jsonPrimitive.content

fun JsonElement.int(): Int = jsonPrimitive.int

fun JsonObject.obj(key: String): JsonObject = getValue(key).jsonObject

fun JsonObject.arr(key: String): JsonArray = getValue(key).jsonArray

fun JsonObject.isNull(key: String): Boolean = this[key] == null || this[key] is JsonNull

/** The generator's sparse landmark lists: {length, fill, set: {index: [x,y,z]}}. */
fun JsonElement.landmarks(): List<Landmark?> {
    val o = jsonObject
    val length = o.getValue("length").int()
    val fill = o["fill"]?.takeIf { it !is JsonNull }?.nums()?.let { Landmark(it[0], it[1], it[2]) }
    val out = MutableList(length) { fill }
    for ((index, value) in o.obj("set")) {
        val xyz = value.nums()
        out[index.toInt()] = Landmark(xyz[0], xyz[1], xyz[2])
    }
    return out
}

/** Bit-exact equality: -0 differs from +0, and NaN equals NaN. */
fun assertSameDouble(expected: Double?, actual: Double?, where: String) {
    if (expected == null || actual == null) {
        assertEquals(where, expected, actual)
        return
    }
    if (expected.isNaN() && actual.isNaN()) return
    if (expected.toRawBits() != actual.toRawBits()) {
        fail("$where: expected $expected (bits ${expected.toRawBits()}), got $actual (bits ${actual.toRawBits()})")
    }
}

fun <T> JsonElement.mapIndexedCases(block: (Int, JsonObject) -> T): List<T> =
    jsonArray.mapIndexed { i, e -> block(i, e.jsonObject) }

val JsonElement.isJsonNull: Boolean get() = this is JsonNull

fun JsonElement.primitiveOrNull(): JsonPrimitive? = if (this is JsonNull) null else jsonPrimitive
