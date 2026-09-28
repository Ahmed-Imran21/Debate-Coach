package com.debatecoach.app.feature.report

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.debatecoach.app.core.Backend
import com.debatecoach.app.core.model.SessionReport
import com.debatecoach.app.core.model.SessionSummary
import com.debatecoach.app.core.net.ApiException
import java.net.URLEncoder
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

const val SESSION_POLL_MS = 4_000L

sealed interface ShareUi {
    data object Loading : ShareUi
    data object Private : ShareUi
    /** The link is only known right after it's created: the server keeps just a hash of the token. */
    data class Shared(val link: String?) : ShareUi
}

data class SessionUiState(
    val summary: SessionSummary? = null,
    val report: SessionReport? = null,
    val error: String? = null,
    val filter: String = "all",
    val share: ShareUi = ShareUi.Loading,
    val shareBusy: Boolean = false,
    val shareError: String? = null,
    val copied: Boolean = false,
    val deleting: Boolean = false,
    val deleted: Boolean = false,
    val deleteError: String? = null,
)

/** The public URL for a share token, on the website (lib/share.ts shareUrl). */
fun shareUrl(website: String, token: String): String =
    "${website.trimEnd('/')}/shared/${URLEncoder.encode(token, "UTF-8").replace("+", "%20")}"

/**
 * app/practice/[id]/page.tsx and components/ShareSection.tsx: polls a
 * session until it's done, then loads the report; share controls.
 */
class SessionViewModel(
    private val backend: Backend,
    private val sessionId: String,
    private val websiteUrl: String,
) : ViewModel() {
    private val _state = MutableStateFlow(SessionUiState())
    val state: StateFlow<SessionUiState> = _state.asStateFlow()
    private var polling: Job? = null
    private var copiedReset: Job? = null

    /** Returns whether to keep polling. */
    suspend fun load(): Boolean = try {
        val current = backend.getSession(sessionId)
        _state.update { it.copy(summary = current, error = null) }
        if (current.status == "completed") {
            val report = backend.getReport(sessionId)
            _state.update { it.copy(report = report) }
            if (_state.value.share == ShareUi.Loading) loadShare()
            false
        } else {
            current.status != "failed"
        }
    } catch (error: Exception) {
        if (error is CancellationException) throw error
        when {
            error is ApiException && error.status == 401 -> false
            error is ApiException && error.status == 404 -> {
                _state.update { it.copy(error = "That session does not exist.") }
                false
            }
            else -> {
                _state.update { it.copy(error = "Could not load this session. Retrying.") }
                true
            }
        }
    }

    /** While the screen is visible: a session finishing elsewhere shows up here. */
    fun startPolling() {
        if (_state.value.report != null) return
        polling?.cancel()
        polling = viewModelScope.launch {
            while (isActive) {
                if (!load()) break
                delay(SESSION_POLL_MS)
            }
        }
    }

    fun stopPolling() {
        polling?.cancel()
        polling = null
    }

    fun setFilter(category: String) = _state.update { it.copy(filter = category) }

    // ---------------------------------------------------------------
    // Sharing
    // ---------------------------------------------------------------

    private suspend fun loadShare() {
        try {
            val status = backend.shareStatus(sessionId)
            _state.update { it.copy(share = if (status.sharing) ShareUi.Shared(null) else ShareUi.Private) }
        } catch (error: Exception) {
            if (error is CancellationException) throw error
            _state.update { it.copy(share = ShareUi.Private, shareError = "Could not load the sharing settings.") }
        }
    }

    private fun runShare(failure: String, action: suspend () -> Unit) {
        if (_state.value.shareBusy) return
        _state.update { it.copy(shareBusy = true, shareError = null) }
        viewModelScope.launch {
            try {
                action()
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                if (!(error is ApiException && error.status == 401)) {
                    _state.update { it.copy(shareError = if (error is ApiException) error.message else failure) }
                }
            } finally {
                _state.update { it.copy(shareBusy = false) }
            }
        }
    }

    /** Creates a link, or replaces the current one (the old link stops working). */
    fun createShareLink() = runShare("Could not create a share link. Try again.") {
        val created = backend.createShareLink(sessionId)
        _state.update { it.copy(share = ShareUi.Shared(shareUrl(websiteUrl, created.token)), copied = false) }
    }

    fun stopSharing() = runShare("Could not stop sharing. Try again.") {
        backend.stopSharing(sessionId)
        _state.update { it.copy(share = ShareUi.Private, copied = false) }
    }

    // ---------------------------------------------------------------
    // Delete (the report's overflow menu)
    // ---------------------------------------------------------------

    fun delete() {
        if (_state.value.deleting) return
        _state.update { it.copy(deleting = true, deleteError = null) }
        viewModelScope.launch {
            try {
                backend.deleteSession(sessionId)
                stopPolling()
                _state.update { it.copy(deleting = false, deleted = true) }
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                val message = when {
                    error is ApiException && error.status == 404 -> null.also { _state.update { s -> s.copy(deleted = true) } }
                    error is ApiException && error.status == 401 -> null
                    else -> "Could not delete that session. Try again."
                }
                _state.update { it.copy(deleting = false, deleteError = message) }
            }
        }
    }

    /** "Copied" for two seconds after copying, as on the web. */
    fun markCopied() {
        _state.update { it.copy(copied = true) }
        copiedReset?.cancel()
        copiedReset = viewModelScope.launch {
            delay(2_000)
            _state.update { it.copy(copied = false) }
        }
    }
}
