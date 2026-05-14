/**
 * clipper.js — Dual-handle video clip seeker.
 *
 * Provides two range inputs for selecting start/end times on a video
 * timeline, with click-to-seek and constraint enforcement.
 */
(function () {
  "use strict";

  const VIDEO_ID = "clip-video";
  const START_ID = "clip-start";
  const END_ID = "clip-end";
  const TIMES_ID = "clip-times";
  const BTN_ID = "create-clip-btn";
  const ERROR_ID = "clip-error";
  const MIN_DURATION = 1; // seconds

  let video = null;
  let startInput = null;
  let endInput = null;
  let timesDisplay = null;
  let btn = null;
  let errorDisplay = null;
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
      formatTime(start) + " / " + formatTime(end) + " (" + formatTime(dur) + ")";
  }

  // ── Constraint enforcement ─────────────────────────────────────

  function constrainHandles() {
    if (!startInput || !endInput) return;
    let start = parseFloat(startInput.value);
    let end = parseFloat(endInput.value);

    // Start must not exceed (end - MIN_DURATION)
    if (start > end - MIN_DURATION) {
      start = Math.max(0, end - MIN_DURATION);
    }
    // End must not be less than (start + MIN_DURATION)
    if (end < start + MIN_DURATION) {
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

  // ── Submit ─────────────────────────────────────────────────────

  async function onSubmit() {
    if (!btn || !startInput || !endInput || !errorDisplay) return;
    const videoId = btn.getAttribute("data-video-id");
    if (!videoId) return;

    const start = parseFloat(startInput.value);
    const end = parseFloat(endInput.value);

    // Client-side validation
    if (end - start < MIN_DURATION) {
      errorDisplay.textContent = "Minimum clip duration is 1 second.";
      return;
    }

    btn.disabled = true;
    btn.textContent = "Creating...";
    errorDisplay.textContent = "";

    try {
      const response = await fetch("/api/video/" + videoId + "/clip", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ start: start, end: end }),
      });

      const data = await response.json();

      if (!response.ok) {
        errorDisplay.textContent = data.error || "Failed to create clip.";
        btn.disabled = false;
        btn.textContent = "Create Clip";
        return;
      }

      // Success — redirect to new clip's detail page
      window.location.href = "/video/" + data.id;
    } catch (err) {
      errorDisplay.textContent = "Network error. Please try again.";
      btn.disabled = false;
      btn.textContent = "Create Clip";
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
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
