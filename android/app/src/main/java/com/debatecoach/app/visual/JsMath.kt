package com.debatecoach.app.visual

import java.math.BigDecimal
import java.math.MathContext
import java.math.RoundingMode

/**
 * JavaScript's number semantics, where they differ from Kotlin's
 * defaults, so the port produces bit-identical results to the web
 * module (VisualParityGoldenTest checks every one of these through the
 * functions that use them).
 */
object JsMath {
    /** Math.asin: V8 uses fdlibm, as does StrictMath. */
    fun asin(x: Double): Double = StrictMath.asin(x)

    /** Math.atan2: fdlibm in both. */
    fun atan2(y: Double, x: Double): Double = StrictMath.atan2(y, x)

    /**
     * Math.hypot exactly as V8 implements it (builtins/math.tq):
     * scale by the largest magnitude, then a Kahan-compensated sum of
     * squares. Not java.lang.Math.hypot, which rounds differently.
     */
    fun hypot(vararg values: Double): Double {
        if (values.isEmpty()) return 0.0
        var oneIsNaN = false
        var max = 0.0
        val abs = DoubleArray(values.size)
        for (i in values.indices) {
            val v = values[i]
            if (v.isNaN()) {
                oneIsNaN = true
            } else {
                abs[i] = kotlin.math.abs(v)
                if (abs[i] > max) max = abs[i]
            }
        }
        if (max == Double.POSITIVE_INFINITY) return Double.POSITIVE_INFINITY
        if (oneIsNaN) return Double.NaN
        if (max == 0.0) return 0.0
        var sum = 0.0
        var compensation = 0.0
        for (a in abs) {
            val n = a / max
            val summand = n * n - compensation
            val preliminary = sum + summand
            compensation = (preliminary - sum) - summand
            sum = preliminary
        }
        return kotlin.math.sqrt(sum) * max
    }

    /**
     * Math.round: nearest integer, ties toward +Infinity, and -0 for
     * inputs in [-0.5, 0). java.lang.Math.round has the same tie rule
     * (and is exact since Java 7 / Android 7+).
     */
    fun round(x: Double): Double {
        if (x.isNaN() || x.isInfinite()) return x
        if (kotlin.math.abs(x) >= 4.503599627370496E15) return x // 2^52: already an integer
        val r = Math.round(x).toDouble()
        return if (r == 0.0 && (x < 0.0 || (x == 0.0 && 1.0 / x < 0.0))) -0.0 else r
    }

    /** Math.min / Math.max: NaN-propagating, -0 < +0. Same as java.lang.Math. */
    fun min(a: Double, b: Double): Double = Math.min(a, b)
    fun max(a: Double, b: Double): Double = Math.max(a, b)

    /**
     * Array.prototype.sort((a, b) => a - b): a stable sort where -0 and
     * +0 compare equal and keep their order (Kotlin's natural Double
     * order would put -0.0 first).
     */
    fun sortNumeric(values: List<Double>): List<Double> = values.sortedWith { a, b ->
        val d = a - b
        when {
            d < 0 -> -1
            d > 0 -> 1
            else -> 0
        }
    }

    /**
     * Number.prototype.toString / JSON.stringify for a finite double:
     * the shortest decimal that round-trips, laid out as ECMAScript
     * specifies (plain between 1e-7 and 1e21, exponent notation
     * outside). NaN and the infinities are JSON null.
     */
    fun toJson(value: Double): String {
        if (value.isNaN() || value.isInfinite()) return "null"
        if (value == 0.0) return "0" // also -0
        val negative = value < 0
        val (digits, n) = shortestDigits(kotlin.math.abs(value))
        val k = digits.length
        val body = when {
            n in k..21 -> digits + "0".repeat(n - k)
            n in 1..21 -> digits.substring(0, n) + "." + digits.substring(n)
            n in -5..0 -> "0." + "0".repeat(-n) + digits
            else -> {
                val e = n - 1
                val sign = if (e >= 0) "+" else "-"
                val mantissa = if (k == 1) digits else digits[0] + "." + digits.substring(1)
                mantissa + "e" + sign + kotlin.math.abs(e)
            }
        }
        return if (negative) "-$body" else body
    }

    /**
     * The shortest digit string s and exponent n with value = 0.s × 10^n
     * that reads back as exactly [value]; among equally short ones, the
     * closest (ECMAScript Number::toString).
     */
    private fun shortestDigits(value: Double): Pair<String, Int> {
        val exact = BigDecimal(value)
        for (precision in 1..17) {
            val rounded = exact.round(MathContext(precision, RoundingMode.HALF_EVEN))
            if (rounded.toDouble() == value) return normalize(rounded)
        }
        return normalize(exact.round(MathContext(17, RoundingMode.HALF_EVEN)))
    }

    private fun normalize(decimal: BigDecimal): Pair<String, Int> {
        val stripped = decimal.stripTrailingZeros()
        val digits = stripped.unscaledValue().abs().toString()
        // value = digits × 10^(-scale) = 0.digits × 10^(len - scale)
        return digits to (digits.length - stripped.scale())
    }
}
