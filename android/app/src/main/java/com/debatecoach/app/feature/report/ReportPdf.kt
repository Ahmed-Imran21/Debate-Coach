package com.debatecoach.app.feature.report

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.pdf.PdfDocument
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import androidx.core.content.res.ResourcesCompat
import com.debatecoach.app.R
import com.debatecoach.app.core.model.CATEGORY_LABEL
import com.debatecoach.app.core.model.SCORE_ORDER
import com.debatecoach.app.core.model.SEVERITY_LABEL
import com.debatecoach.app.core.model.SessionReport
import com.debatecoach.app.core.util.formatRecordedLong
import com.debatecoach.app.core.util.jsRound
import java.io.File

/**
 * "Export as PDF": the report in the website's print layout
 * (globals.css @media print), drawn with Android's PdfDocument. A4,
 * margins 16mm × 14mm, black on white, 10.5pt text; bars outlined with
 * a solid fill; severity in greys (the finding also names it in words);
 * a finding is never split across pages. Like the website's printout,
 * it leaves out the share controls, the timeline and the audio player,
 * and shows every finding regardless of the on-screen filter.
 */
object ReportPdf {
    private const val PAGE_W = 595 // A4 in points
    private const val PAGE_H = 842
    private const val MARGIN_X = 40f // 14mm
    private const val MARGIN_Y = 45f // 16mm
    private const val CONTENT_W = PAGE_W - 2 * MARGIN_X

    fun write(context: Context, report: SessionReport): File {
        val serif = ResourcesCompat.getFont(context, R.font.newsreader) ?: Typeface.SERIF
        val sans = ResourcesCompat.getFont(context, R.font.ibm_plex_sans) ?: Typeface.SANS_SERIF
        val doc = PdfDocument()
        val writer = Writer(doc, serif, sans)
        try {
            writer.render(report)
            writer.finish()
            val dir = File(context.cacheDir, "reports").apply { mkdirs() }
            dir.listFiles()?.forEach { it.delete() }
            val safeName = (report.title?.takeIf { it.isNotBlank() } ?: "Debate Coach report")
                .replace(Regex("[^A-Za-z0-9 _-]"), "").trim().ifEmpty { "Debate Coach report" }.take(60)
            val file = File(dir, "$safeName.pdf")
            file.outputStream().use { doc.writeTo(it) }
            return file
        } finally {
            doc.close()
        }
    }

    private class Writer(private val doc: PdfDocument, private val serif: Typeface, private val sans: Typeface) {
        private var pageNumber = 0
        private var page: PdfDocument.Page? = null
        private lateinit var canvas: Canvas
        private var y = MARGIN_Y

        private val body = paint(sans, 10.5f, Color.BLACK)
        private val meta = paint(sans, 9.5f, Color.rgb(0x33, 0x33, 0x33))
        private val h1 = paint(serif, 22f, Color.BLACK)
        private val h2 = paint(serif, 14.5f, Color.BLACK)
        private val h3 = paint(sans, 11.5f, Color.BLACK).apply { isFakeBoldText = true }
        private val quote = paint(serif, 11f, Color.BLACK)
        private val figureValue = paint(serif, 17f, Color.BLACK)

        private fun paint(face: Typeface, size: Float, color: Int) = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
            typeface = face
            textSize = size
            this.color = color
        }

        private fun newPage() {
            page?.let { doc.finishPage(it) }
            pageNumber += 1
            val p = doc.startPage(PdfDocument.PageInfo.Builder(PAGE_W, PAGE_H, pageNumber).create())
            page = p
            canvas = p.canvas
            y = MARGIN_Y
        }

        fun finish() {
            page?.let { doc.finishPage(it) }
            page = null
        }

        private fun layout(text: String, paint: TextPaint, width: Float = CONTENT_W): StaticLayout =
            StaticLayout.Builder.obtain(text, 0, text.length, paint, width.toInt())
                .setAlignment(Layout.Alignment.ALIGN_NORMAL)
                .setLineSpacing(0f, 1.25f)
                .build()

        /** Keeps a block of this height on one page (break-inside: avoid). */
        private fun ensure(height: Float) {
            if (page == null || y + height > PAGE_H - MARGIN_Y) newPage()
        }

        private fun text(text: String, paint: TextPaint, after: Float = 6f, x: Float = MARGIN_X, width: Float = CONTENT_W) {
            val l = layout(text, paint, width)
            ensure(l.height.toFloat())
            canvas.save()
            canvas.translate(x, y)
            l.draw(canvas)
            canvas.restore()
            y += l.height + after
        }

        /** A heading stays with what follows it (break-after: avoid). */
        private fun heading(text: String, paint: TextPaint = h2, keepWith: Float = 60f) {
            val l = layout(text, paint)
            ensure(l.height + keepWith)
            y += 10f
            text(text, paint, after = 8f)
        }

        fun render(r: SessionReport) {
            newPage()
            val recorded = formatRecordedLong(r.createdAt)
            text(r.title?.takeIf { it.isNotEmpty() } ?: "Session of $recorded", h1, after = 6f)
            val lines = buildList {
                add("Recorded $recorded")
                r.motion?.let { add("Motion: ${it.description}") }
                motionFallbackNote(r.motion != null, r.motionNotApplied)?.let { add(it) }
            }
            text(lines.joinToString("\n"), meta, after = 16f)

            figures(figuresFor(r))
            visual(r)
            moments(r)
            scores(r)
            findings(r)
        }

        private fun figures(figures: List<Figure>) {
            val cols = 3
            val cellW = CONTENT_W / cols
            val cellH = 52f
            val rows = (figures.size + cols - 1) / cols
            ensure(rows * cellH + 18f)
            val border = Paint().apply { color = Color.rgb(0x99, 0x99, 0x99); style = Paint.Style.STROKE; strokeWidth = 0.75f }
            figures.forEachIndexed { i, f ->
                val x = MARGIN_X + (i % cols) * cellW
                val top = y + (i / cols) * cellH
                canvas.drawRect(x, top, x + cellW, top + cellH, border)
                canvas.drawText(f.value, x + 10f, top + 24f, figureValue)
                canvas.drawText(f.label, x + 10f, top + 41f, meta)
            }
            y += rows * cellH + 18f
        }

        private fun visual(r: SessionReport) {
            when (val section = visualSection(r)) {
                VisualSection.Hidden -> Unit
                is VisualSection.Message -> {
                    heading("Visual delivery")
                    text(section.text, body, after = 12f)
                }
                is VisualSection.Metrics -> {
                    heading("Visual delivery")
                    section.rows.forEach { row ->
                        val block = listOfNotNull(
                            "${row.label}: ${row.value}" + (row.confidence?.let { " ($it)" } ?: ""),
                            row.definition,
                        ).joinToString("\n")
                        text(block, body, after = 6f)
                    }
                    listOfNotNull(section.faceMessage, section.handsMessage).forEach { text(it, meta) }
                    section.warnings.forEach { text(it, meta) }
                    if (section.coachingFailed) text("Coaching notes for your visual delivery couldn’t be generated for this session. The measurements above are unaffected.", meta)
                    section.sessionFeedback.forEach { (coaching, _) -> text(coaching, body) }
                    y += 6f
                }
            }
        }

        private fun moments(r: SessionReport) {
            val entries = keyMoments(r)
            if (entries.isEmpty()) return
            heading("Key moments")
            entries.forEach { e ->
                val block = buildList {
                    add(e.meta)
                    if (e.moment.excerptText.isNotEmpty()) add("“${e.moment.excerptText}”")
                    e.facts.forEach { add("• $it") }
                    e.coaching?.let { add(it) }
                }.joinToString("\n")
                marked(if (e.positive) Severity.POSITIVE else Severity.MEDIUM) { width -> layout(block, body, width) }
            }
        }

        private fun scores(r: SessionReport) {
            heading("Scores by category", keepWith = 6 * 24f)
            val labelW = 110f
            val valueW = 34f
            val trackW = CONTENT_W - labelW - valueW - 12f
            val outline = Paint().apply { color = Color.BLACK; style = Paint.Style.STROKE; strokeWidth = 0.75f }
            val fill = Paint().apply { color = Color.BLACK; style = Paint.Style.FILL }
            SCORE_ORDER.forEach { category ->
                ensure(24f)
                val raw = r.scores[category]
                val notScored = r.scores.containsKey(category) && raw == null
                canvas.drawText(CATEGORY_LABEL[category].orEmpty(), MARGIN_X, y + 13f, body)
                if (notScored) {
                    canvas.drawText("Not scored: nothing to rebut", MARGIN_X + labelW, y + 13f, meta)
                } else {
                    val value = (raw ?: 0.0).coerceIn(0.0, 100.0)
                    val left = MARGIN_X + labelW
                    canvas.drawRect(left, y + 5f, left + trackW, y + 13f, outline)
                    canvas.drawRect(left, y + 5f, left + (trackW * value / 100).toFloat(), y + 13f, fill)
                    canvas.drawText(jsRound(raw ?: 0.0).toString(), left + trackW + 12f, y + 13f, meta)
                }
                y += 24f
            }
            y += 4f
            text(
                "Delivery is arithmetic over the audio. The other five come from a language model reading the transcript, so treat them as a second opinion rather than a mark. Rebuttal isn't scored when there was nothing to rebut, and doesn't count toward the overall.",
                meta,
                after = 12f,
            )
        }

        private fun findings(r: SessionReport) {
            heading("Findings")
            visibleFindings(r.feedback, "all").forEach { item ->
                val severity = when (item.severity) {
                    "high" -> Severity.HIGH
                    "medium" -> Severity.MEDIUM
                    "positive" -> Severity.POSITIVE
                    else -> Severity.LOW
                }
                marked(severity) { width ->
                    val sb = StringBuilder()
                    sb.append(item.title).append('\n')
                    sb.append("${CATEGORY_LABEL[item.category] ?: item.category}. ${SEVERITY_LABEL[item.severity] ?: item.severity}.").append('\n')
                    sb.append(item.issue)
                    item.evidence.forEach { sb.append("\n“").append(it).append('”') }
                    item.explanation?.let { sb.append('\n').append(it) }
                    item.recommendation?.let { sb.append('\n').append(it) }
                    layout(sb.toString(), body, width)
                }
            }
        }

        private enum class Severity { HIGH, MEDIUM, LOW, POSITIVE }

        /** A finding-style block with its severity bar, kept on one page. */
        private fun marked(severity: Severity, build: (Float) -> StaticLayout) {
            val barW = 4f
            val gap = 12f
            val l = build(CONTENT_W - barW - gap)
            val height = l.height.toFloat()
            ensure(height + 14f)
            val rule = Paint().apply { color = Color.rgb(0xCC, 0xCC, 0xCC); strokeWidth = 0.5f }
            canvas.drawLine(MARGIN_X, y, MARGIN_X + CONTENT_W, y, rule)
            y += 7f
            val bar = Paint().apply {
                style = Paint.Style.FILL
                color = when (severity) {
                    Severity.HIGH -> Color.BLACK
                    Severity.MEDIUM -> Color.rgb(0x66, 0x66, 0x66)
                    Severity.LOW -> Color.rgb(0xCC, 0xCC, 0xCC)
                    Severity.POSITIVE -> Color.WHITE
                }
            }
            canvas.drawRect(MARGIN_X, y, MARGIN_X + barW, y + height, bar)
            if (severity == Severity.POSITIVE) {
                canvas.drawRect(MARGIN_X, y, MARGIN_X + barW, y + height, Paint().apply { color = Color.BLACK; style = Paint.Style.STROKE; strokeWidth = 0.75f })
            }
            canvas.save()
            canvas.translate(MARGIN_X + barW + gap, y)
            l.draw(canvas)
            canvas.restore()
            y += height + 7f
        }
    }
}
