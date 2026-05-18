/**
 * clipper.js — Dual-handle video clip seeker.
 *
 * Provides two range inputs for selecting start/end times on a video
 * timeline, with click-to-seek and constraint enforcement.
 */
(function () {
  "use strict";

  // Translation helper (falls back to key if translation missing)
  function _(key) {
    return (window.TRANSLATIONS && window.TRANSLATIONS[key]) || key;
  }

  const VIDEO_ID = "clip-video";
  const START_ID = "clip-start";
  const END_ID = "clip-end";
  const TIMES_ID = "clip-times";
  const BTN_ID = "create-clip-btn";
  const ERROR_ID = "clip-error";
  const SET_BEGIN_ID = "set-begin-btn";
  const SET_END_ID = "set-end-btn";
  const CUT_BTN_ID = "cut-btn";
  const CUT_PROGRESS_ID = "cut-progress";
  const MIN_DURATION = 1; // seconds

  let video = null;
  let startInput = null;
  let endInput = null;
  let timesDisplay = null;
  let btn = null;
  let errorDisplay = null;
  let setBeginBtn = null;
  let setEndBtn = null;
  let cutBtn = null;
  let cutProgress = null;
  let duration = 0;

  // ── Display update ────────────────────────────────────────────

  function formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    if (m > 0) {
      return m + "m " + (s < 10 ? "0" : "") + s.toFixed(1) + "s";
    }
    return s.toFixed(1) + "s";
  }

  function updateDisplay() {
    if (!startInput || !endInput || !timesDisplay) return;
    const start = parseFloat(startInput.value);
    const end = parseFloat(endInput.value);
    const dur = Math.max(0, end - start);
    timesDisplay.textContent =
      formatTime(start) +
      " / " +
      formatTime(end) +
      " (" +
      formatTime(dur) +
      ")";
  }

  // ── Constraint enforcement ─────────────────────────────────────

  function constrainHandles(e) {
    if (!startInput || !endInput) return;
    let start = parseFloat(startInput.value);
    let end = parseFloat(endInput.value);

    // Start must not exceed (end - MIN_DURATION)
    if (e.currentTarget == endInput && start > end - MIN_DURATION) {
      start = Math.max(0, end - MIN_DURATION);
    }
    // End must not be less than (start + MIN_DURATION)
    if (e.currentTarget == startInput && end < start + MIN_DURATION) {
      end = Math.min(duration, start + MIN_DURATION);
    }

    // Clamp to video duration
    start = Math.min(start, duration);
    end = Math.min(end, duration);

    startInput.value = start.toFixed(1);
    endInput.value = end.toFixed(1);

    updateDisplay();
  }

  // ── Seek video on range click ──────────────────────────────────

  function seekVideo(time) {
    if (video) {
      video.currentTime = time;
    }
  }

  function onRangeClick(event) {
    if (!video || !duration) return;
    const range = event.currentTarget;
    const rect = range.getBoundingClientRect();
    const clickX = event.clientX - rect.left;
    const ratio = clickX / rect.width;
    const time = ratio * duration;
    seekVideo(time);
  }

  // ── Set handle to current video time ───────────────────────────

  function setHandleToCurrentTime(isStart) {
    if (!video || !duration) return;
    const time = video.currentTime;

    if (isStart) {
      let start = time;
      let end = parseFloat(endInput.value);
      // If start would leave less than MIN_DURATION, push end forward
      if (start > end - MIN_DURATION) {
        end = Math.min(duration, start + MIN_DURATION);
        // If pushing pushed end past max, clamp start back instead
        if (end > duration) {
          end = duration;
          start = Math.max(0, end - MIN_DURATION);
        }
      }
      startInput.value = start.toFixed(1);
      endInput.value = end.toFixed(1);
    } else {
      let end = time;
      let start = parseFloat(startInput.value);
      // If end would leave less than MIN_DURATION, push start back
      if (end < start + MIN_DURATION) {
        start = Math.max(0, end - MIN_DURATION);
        // If pushing pushed start below 0, clamp end forward instead
        if (start < 0) {
          start = 0;
          end = Math.min(duration, start + MIN_DURATION);
        }
      }
      startInput.value = start.toFixed(1);
      endInput.value = end.toFixed(1);
    }

    updateDisplay();
    seekVideo(time);
  }

  // ── Submit ─────────────────────────────────────────────────────

  async function onSubmit() {
    if (!btn || !startInput || !endInput || !errorDisplay) return;
    const videoId = btn.getAttribute("data-video-id");
    if (!videoId) return;

    const start = parseFloat(startInput.value);
    const end = parseFloat(endInput.value);

    // Client-side validation
    if (end - start < MIN_DURATION) {
      errorDisplay.textContent = _("clip.min_duration");
      return;
    }

    btn.disabled = true;
    btn.textContent = _("clip.creating");
    errorDisplay.textContent = "";

    try {
      const response = await fetch("/api/videos/" + videoId + "/clip", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ start: start, end: end }),
      });

      const data = await response.json();

      if (!response.ok) {
        errorDisplay.textContent = data.error || _("clip.failed");
        btn.disabled = false;
        btn.textContent = _("btn.create_clip");
        return;
      }

      // Success — redirect to new clip's detail page
      window.location.href = "/videos/" + data.id;
    } catch (err) {
      errorDisplay.textContent = _("clip.network_error");
      btn.disabled = false;
      btn.textContent = _("btn.create_clip");
    }
  }

  // ── Cut (in-place) ──────────────────────────────────────────────

  async function onCut() {
    if (!cutBtn || !startInput || !endInput || !errorDisplay || !cutProgress) return;
    const videoId = cutBtn.getAttribute("data-video-id");
    if (!videoId) return;

    const start = parseFloat(startInput.value);
    const end = parseFloat(endInput.value);

    // Client-side validation
    if (end - start < MIN_DURATION) {
      errorDisplay.textContent = _("clip.min_duration");
      return;
    }

    // Confirm destructive action
    if (!confirm(_("clip.cut_confirm"))) return;

    cutBtn.disabled = true;
    cutBtn.textContent = _("clip.cutting");
    cutProgress.textContent = _("clip.cutting");
    cutProgress.classList.remove("hidden");
    errorDisplay.textContent = "";

    try {
      const response = await fetch("/api/videos/" + videoId + "/cut", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ start: start, end: end }),
      });

      const data = await response.json();

      if (!response.ok) {
        errorDisplay.textContent = data.error || _("clip.cut_failed");
        cutBtn.disabled = false;
        cutBtn.textContent = _("clip.cut");
        cutProgress.classList.add("hidden");
        return;
      }

      // Success — redirect back to the (now trimmed) video detail
      window.location.href = "/videos/" + data.id;
    } catch (err) {
      errorDisplay.textContent = _("clip.network_error");
      cutBtn.disabled = false;
      cutBtn.textContent = _("clip.cut");
      cutProgress.classList.add("hidden");
    }
  }

  // ── Init ───────────────────────────────────────────────────────

  function init() {
    video = document.getElementById(VIDEO_ID);
    startInput = document.getElementById(START_ID);
    endInput = document.getElementById(END_ID);
    timesDisplay = document.getElementById(TIMES_ID);
    btn = document.getElementById(BTN_ID);
    errorDisplay = document.getElementById(ERROR_ID);
    setBeginBtn = document.getElementById(SET_BEGIN_ID);
    setEndBtn = document.getElementById(SET_END_ID);
    cutBtn = document.getElementById(CUT_BTN_ID);
    cutProgress = document.getElementById(CUT_PROGRESS_ID);

    if (!video || !startInput || !endInput) return;

    // Wait for video metadata to get duration
    video.addEventListener("loadedmetadata", function () {
      duration = video.duration || 0;
      if (duration > 0) {
        startInput.max = duration;
        endInput.max = duration;
        endInput.value = Math.min(30, duration).toFixed(1);
        updateDisplay();
      }
    });

    // If video is already loaded
    if (video.readyState >= 1 && video.duration) {
      duration = video.duration;
      startInput.max = duration;
      endInput.max = duration;
      endInput.value = Math.min(30, duration).toFixed(1);
      updateDisplay();
    }

    // Constraint handling
    startInput.addEventListener("input", constrainHandles);
    endInput.addEventListener("input", constrainHandles);

    // Click-to-seek
    startInput.addEventListener("click", onRangeClick);
    endInput.addEventListener("click", onRangeClick);

    // Submit button
    if (btn) {
      btn.addEventListener("click", onSubmit);
    }

    // Cut button
    if (cutBtn) {
      cutBtn.addEventListener("click", onCut);
    }

    // Set-begin / set-end buttons
    if (setBeginBtn) {
      setBeginBtn.addEventListener("click", function () {
        setHandleToCurrentTime(true);
      });
    }
    if (setEndBtn) {
      setEndBtn.addEventListener("click", function () {
        setHandleToCurrentTime(false);
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
