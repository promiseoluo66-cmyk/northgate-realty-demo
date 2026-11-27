(() => {
  "use strict";

  let currentProject = null;
  let currentRevision = null;
  let selectedClipId = "";
  let selectedClipIds = new Set();
  let activeView = "timeline";
  let playheadUs = 0;
  let timelinePixelsPerSecond = 46;
  let skipClipClickUntil = 0;
  let keyframeClipboard = [];

  const byId = (id) => document.getElementById(id);

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function formatTime(microseconds) {
    const totalSeconds = Math.max(0, Math.floor(Number(microseconds || 0) / 1000000));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return hours > 0
      ? [hours, minutes, seconds].map((value) => String(value).padStart(2, "0")).join(":")
      : [minutes, seconds].map((value) => String(value).padStart(2, "0")).join(":");
  }

  function formatBytes(value) {
    const bytes = Number(value || 0);
    if (!Number.isFinite(bytes) || bytes <= 0) return "Size unavailable";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function flattenClips(project) {
    const rows = [];
    (Array.isArray(project.tracks) ? project.tracks : []).forEach((track) => {
      (Array.isArray(track.clips) ? track.clips : []).forEach((clip) => {
        rows.push({ track, clip });
      });
    });
    return rows;
  }

  function findSelectedClip() {
    if (!currentProject || !selectedClipId) return null;
    return flattenClips(currentProject).find((item) => item.clip.id === selectedClipId) || null;
  }

  function secondsToUs(value) {
    const seconds = Number(value);
    if (!Number.isFinite(seconds) || seconds < 0) throw new Error("Enter a valid time in seconds.");
    return Math.round(seconds * 1000000);
  }

  function setPlayhead(value, syncPreview = true) {
    const maxUs = flattenClips(currentProject || {}).reduce((end, item) =>
      Math.max(end, Number(item.clip.start_us || 0) + Number(item.clip.duration_us || 0)), 0);
    playheadUs = Math.max(0, Math.min(Number(value) || 0, maxUs || Number(value) || 0));
    const slider = byId("timeline-seek");
    const output = byId("playhead-time");
    if (slider) {
      slider.max = String(Math.max(1000000, maxUs));
      slider.value = String(playheadUs);
    }
    if (output) output.textContent = formatTime(playheadUs);
    document.querySelectorAll(".timeline-playhead").forEach((line) => {
      line.style.left = (playheadUs / 1000000 * timelinePixelsPerSecond) + "px";
    });
    if (syncPreview) {
      const video = byId("studio-preview");
      if (video && Number.isFinite(video.duration)) {
        const previewMediaId = video.dataset.mediaId || "source-video";
        const mainClip = flattenClips(currentProject || {}).find(({clip}) =>
          clip.kind === "video" && clip.media_id === previewMediaId &&
          playheadUs >= Number(clip.start_us || 0) &&
          playheadUs <= Number(clip.start_us || 0) + Number(clip.duration_us || 0));
        const desired = video.dataset.previewMode === "composite"
          ? playheadUs / 1000000
          : mainClip
            ? (Number(mainClip.clip.source_in_us || 0) +
              (playheadUs - Number(mainClip.clip.start_us || 0)) *
              Number(mainClip.clip.playback_rate || 1)) / 1000000
            : 0;
        const safeTime = Math.max(0, Math.min(Math.max(0, video.duration - 0.04), desired));
        if (Math.abs(video.currentTime - safeTime) > 0.08) video.currentTime = safeTime;
      }
    }
  }

  async function submitOperations(toolCalls, confirmedTools = []) {
    if (!Array.isArray(toolCalls) || !toolCalls.length) return;
    if (typeof window.applyStudioOperations !== "function") {
      throw new Error("The authenticated Studio editing connection is not ready.");
    }
    return window.applyStudioOperations(toolCalls, confirmedTools);
  }

  function fillTrackSelector() {
    const select = byId("manage-track");
    if (!select || !currentProject) return;
    const previous = select.value;
    select.replaceChildren();
    (currentProject.tracks || []).slice()
      .sort((a, b) => Number(a.order || 0) - Number(b.order || 0))
      .forEach((track) => {
        const option = element("option", "",
          track.name + " · " + track.type +
          (track.solo ? " · SOLO" : "") +
          (track.visible === false ? " · HIDDEN" : "") +
          (track.muted ? " · MUTED" : "") +
          (track.enabled === false ? " · OFF" : ""));
        option.value = track.id;
        select.append(option);
      });
    if ((currentProject.tracks || []).some((track) => track.id === previous)) select.value = previous;
    select.dispatchEvent(new Event("change"));
  }

  function selectedTrack() {
    if (!currentProject) return null;
    const id = byId("manage-track")?.value;
    return (currentProject.tracks || []).find((track) => track.id === id) || null;
  }

  function snapStart(proposedUs, trackId, clipId) {
    if (byId("timeline-snap-toggle")?.checked === false || !currentProject) return proposedUs;
    let best = proposedUs;
    let bestDistance = 150000;
    const selected = flattenClips(currentProject).find((item) => item.clip.id === clipId);
    const groupId = selected?.clip.group_id;
    const excluded = new Set([clipId]);
    if (groupId) (currentProject.clip_groups || []).filter((g) => g.id === groupId)
      .forEach((g) => (g.clip_ids || []).forEach((id) => excluded.add(id)));
    const candidates = [playheadUs, ...(currentProject.markers || []).map((m) => Number(m.time_us || 0))];
    (currentProject.tracks || []).filter((track) => track.locked !== true).forEach((track) => {
      (track.clips || []).filter((clip) => !excluded.has(clip.id)).forEach((clip) => {
        candidates.push(Number(clip.start_us || 0));
        candidates.push(Number(clip.start_us || 0) + Number(clip.duration_us || 0));
      });
    });
    candidates.forEach((candidate) => {
      const distance = Math.abs(candidate - proposedUs);
      if (distance < bestDistance) { best = candidate; bestDistance = distance; }
    });
    return best;
  }

  function bindClipDrag(button, clip, originalTrack, lane) {
    let gesture = null;
    button.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || originalTrack.locked) return;
      const handle = event.target.closest(".clip-handle");
      gesture = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        mode: handle?.classList.contains("clip-handle-left") ? "trim-left" :
          handle?.classList.contains("clip-handle-right") ? "trim-right" : "move",
        moved: false,
        originalStart: Number(clip.start_us || 0),
        originalDuration: Number(clip.duration_us || 0),
        sourceIn: Number(clip.source_in_us || 0),
        sourceOut: Number(clip.source_out_us ??
          (clip.source_in_us || 0) + Number(clip.duration_us || 0) * Number(clip.playback_rate || 1)),
        trackId: originalTrack.id,
        startLeft: Number(clip.start_us || 0) / 1000000 * timelinePixelsPerSecond,
        startWidth: Number(clip.duration_us || 0) / 1000000 * timelinePixelsPerSecond
      };
      try { button.setPointerCapture(event.pointerId); } catch (_) {}
    });
    button.addEventListener("pointermove", (event) => {
      if (!gesture || gesture.pointerId !== event.pointerId) return;
      const dx = event.clientX - gesture.startX;
      if (!gesture.moved && Math.abs(dx) < 4) return;
      gesture.moved = true;
      event.preventDefault();
      if (gesture.mode === "move") button.style.left = Math.max(0, gesture.startLeft + dx) + "px";
      else if (gesture.mode === "trim-left") {
        const width = Math.max(20, gesture.startWidth - dx);
        button.style.left = Math.max(0, gesture.startLeft + dx) + "px";
        button.style.width = width + "px";
      } else button.style.width = Math.max(20, gesture.startWidth + dx) + "px";
    });
    button.addEventListener("pointerup", async (event) => {
      if (!gesture || gesture.pointerId !== event.pointerId) return;
      const state = gesture;
      gesture = null;
      if (!state.moved) return;
      event.preventDefault();
      skipClipClickUntil = Date.now() + 500;
      const deltaUs = Math.round((event.clientX - state.startX) / timelinePixelsPerSecond * 1000000);
      const drop = document.elementFromPoint(event.clientX, event.clientY)?.closest(".timeline-lane");
      const targetTrackId = drop?.dataset.trackId || state.trackId;
      try {
        if (state.mode === "move") {
          const startUs = snapStart(Math.max(0, state.originalStart + deltaUs), targetTrackId, clip.id);
          await submitOperations([{
            name: "timeline.move_clip",
            arguments: { clip_id: clip.id, start_us: startUs, track_id: targetTrackId }
          }]);
        } else {
          if (clip.kind === "text") throw new Error("Text clips cannot be source-trimmed.");
          const rate = Number(clip.playback_rate || 1);
          if (state.mode === "trim-left") {
            const sourceIn = Math.max(0, state.sourceIn + Math.round(deltaUs * rate));
            const actualDelta = Math.round((sourceIn - state.sourceIn) / rate);
            const sourceOut = state.sourceOut;
            if (sourceOut <= sourceIn || state.originalStart + actualDelta < 0) {
              throw new Error("That trim would create an invalid clip range.");
            }
            await submitOperations([
              { name: "timeline.trim_clip", arguments: {
                clip_id: clip.id, source_in_us: sourceIn, source_out_us: sourceOut
              }},
              { name: "timeline.move_clip", arguments: {
                clip_id: clip.id, start_us: state.originalStart + actualDelta
              }}
            ]);
          } else {
            const asset = (currentProject.assets || []).find((item) => item.id === clip.media_id);
            const cap = asset?.duration_us ? Number(asset.duration_us) : Number.MAX_SAFE_INTEGER;
            const sourceOut = Math.min(cap, state.sourceOut + Math.round(deltaUs * rate));
            if (sourceOut <= state.sourceIn) throw new Error("That trim would make the clip shorter than its source in point.");
            await submitOperations([{ name: "timeline.trim_clip", arguments: {
              clip_id: clip.id, source_in_us: state.sourceIn, source_out_us: sourceOut
            }}]);
          }
        }
      } catch (error) {
        const status = byId("render-status");
        if (status) {
          status.textContent = error.message;
          status.className = "status error";
        }
        renderTimeline();
      }
    });
    button.addEventListener("pointercancel", () => {
      gesture = null;
      renderTimeline();
    });
  }

  function renderKeyframeGraph() {
    const host = byId("keyframe-graph");
    if (!host) return;
    host.replaceChildren();
    const item = findSelectedClip();
    const property = byId("keyframe-property")?.value || "scale_x";
    if (!item) {
      host.append(element("p", "graph-hint", "Select a clip to inspect or edit its keyframe curve."));
      return;
    }
    const clip = item.clip;
    const keyframes = (clip.keyframes || [])
      .filter((frame) => frame.property === property)
      .slice().sort((a, b) => Number(a.time_us) - Number(b.time_us));
    const duration = Math.max(1, Number(clip.duration_us || 1));
    const zoomControl = byId("keyframe-graph-zoom");
    const panControl = byId("keyframe-graph-pan");
    const zoom = Math.max(1, Number(zoomControl?.value || 100) / 100);
    const panRatio = Math.max(0, Math.min(1, Number(panControl?.value || 0) / 100));
    const visibleDuration = duration / zoom;
    const panUs = Math.max(0, duration - visibleDuration) * panRatio;
    const limits = {
      position_x: [-1000, 1000], position_y: [-1000, 1000],
      scale_x: [0, 4], scale_y: [0, 4], rotation_deg: [-180, 180],
      opacity: [0, 1], playback_rate: [0.05, 16], volume_db: [-96, 24],
      crop_x: [0, 1], crop_y: [0, 1], crop_width: [0.001, 1], crop_height: [0.001, 1]
    };
    let [minValue, maxValue] = limits[property] || [0, 1];
    const values = keyframes.map((frame) => Number(frame.value)).filter(Number.isFinite);
    if (values.length) {
      minValue = Math.min(minValue, ...values);
      maxValue = Math.max(maxValue, ...values);
    }
    if (maxValue <= minValue) maxValue = minValue + 1;
    const width = 560, height = 190, left = 38, right = 14, top = 14, bottom = 28;
    const plotWidth = width - left - right, plotHeight = height - top - bottom;
    const xFor = (time) => left + ((Number(time) - panUs) / visibleDuration) * plotWidth;
    const yFor = (value) => top + ((maxValue - Number(value)) / (maxValue - minValue)) * plotHeight;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 " + width + " " + height);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", property + " keyframe graph for " + clip.id);
    const svgNode = (tag, attributes = {}) => {
      const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
      Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
      return node;
    };
    for (let index = 0; index <= 4; index += 1) {
      const y = top + plotHeight * index / 4;
      svg.append(svgNode("line", {x1:left,y1:y,x2:width-right,y2:y,class:"graph-grid"}));
      const value = maxValue - (maxValue - minValue) * index / 4;
      const label = svgNode("text", {x:left-6,y:y+3,"text-anchor":"end",class:"graph-label"});
      label.textContent = Number(value.toFixed(2)).toString();
      svg.append(label);
    }
    for (let index = 0; index <= 4; index += 1) {
      const x = left + plotWidth * index / 4;
      svg.append(svgNode("line", {x1:x,y1:top,x2:x,y2:height-bottom,class:"graph-grid"}));
      const seconds = (panUs + visibleDuration * index / 4) / 1000000;
      const label = svgNode("text", {x,y:height-8,"text-anchor":"middle",class:"graph-label"});
      label.textContent = formatTime(seconds * 1000000);
      svg.append(label);
    }
    if (keyframes.length) {
      const points = keyframes.map((frame) => xFor(frame.time_us) + "," + yFor(frame.value)).join(" ");
      svg.append(svgNode("polyline", {points,class:"graph-line"}));
    }
    keyframes.forEach((frame) => {
      const point = svgNode("circle", {
        cx:xFor(frame.time_us),cy:yFor(frame.value),r:7,class:"graph-point",
        tabindex:0,role:"slider",
        "aria-label":property+" at "+formatTime(frame.time_us)+", value "+frame.value,
        "aria-valuemin":minValue,"aria-valuemax":maxValue,"aria-valuenow":frame.value
      });
      point.addEventListener("click", () => {
        if (byId("keyframe-time")) byId("keyframe-time").value = String(Number(frame.time_us) / 1000000);
        if (byId("keyframe-value")) byId("keyframe-value").value = String(frame.value);
      });
      point.addEventListener("pointerdown", (event) => {
        event.stopPropagation();
        event.preventDefault();
        try { point.setPointerCapture(event.pointerId); } catch (_) {}
        const update = (moveEvent) => {
          const rect = svg.getBoundingClientRect();
          const scaleX = width / Math.max(1, rect.width);
          const scaleY = height / Math.max(1, rect.height);
          const localX = (moveEvent.clientX - rect.left) * scaleX;
          const localY = (moveEvent.clientY - rect.top) * scaleY;
          const boundedX = Math.max(left, Math.min(width-right, localX));
          const boundedY = Math.max(top, Math.min(height-bottom, localY));
          const nextTime = Math.round(Math.max(0, Math.min(duration,
            panUs+((boundedX-left)/plotWidth)*visibleDuration)));
          const nextValue = maxValue - ((boundedY-top)/plotHeight)*(maxValue-minValue);
          point.setAttribute("cx", String(boundedX));
          point.setAttribute("cy", String(boundedY));
          point.setAttribute("aria-valuenow", String(nextValue));
          point.dataset.nextValue = String(nextValue);
          point.dataset.nextTime = String(nextTime);
        };
        const finish = async (upEvent) => {
          point.removeEventListener("pointermove", update);
          point.removeEventListener("pointerup", finish);
          point.removeEventListener("pointercancel", cancel);
          const nextValue = Number(point.dataset.nextValue);
          const nextTime = Number(point.dataset.nextTime);
          delete point.dataset.nextValue;
          delete point.dataset.nextTime;
          const movedTime = Number.isSafeInteger(nextTime) && nextTime !== Number(frame.time_us);
          const changedValue = Number.isFinite(nextValue) && Math.abs(nextValue-Number(frame.value)) > 0.0001;
          if (movedTime || changedValue) {
            const calls = [];
            if (movedTime) calls.push({name:"animation.remove_keyframe",arguments:{
              clip_id:clip.id,property,time_us:Number(frame.time_us)
            }});
            const args = {
              clip_id:clip.id,property,time_us:movedTime?nextTime:Number(frame.time_us),
              value:changedValue?Number(nextValue.toFixed(4)):Number(frame.value),
              interpolation:frame.interpolation || "linear"
            };
            if (frame.bezier) args.bezier = frame.bezier;
            calls.push({name:"animation.set_keyframe",arguments:args});
            try { await submitOperations(calls); }
            catch (error) {
              const status = byId("render-status");
              if (status) { status.textContent=error.message; status.className="status error"; }
              renderKeyframeGraph();
            }
          } else renderKeyframeGraph();
        };
        const cancel = () => {
          point.removeEventListener("pointermove", update);
          point.removeEventListener("pointerup", finish);
          point.removeEventListener("pointercancel", cancel);
          renderKeyframeGraph();
        };
        point.addEventListener("pointermove", update);
        point.addEventListener("pointerup", finish);
        point.addEventListener("pointercancel", cancel);
      });
      point.addEventListener("keydown", async (event) => {
        if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
        event.preventDefault();
        const step = property === "opacity" ? 0.01 : property === "playback_rate" ? 0.05 : 1;
        const delta = event.key === "ArrowUp" ? step : -step;
        const nextValue = Math.max(minValue, Math.min(maxValue, Number(frame.value)+delta));
        const args = {clip_id:clip.id,property,time_us:Number(frame.time_us),
          value:Number(nextValue.toFixed(4)),interpolation:frame.interpolation || "linear"};
        if (frame.bezier) args.bezier=frame.bezier;
        try { await submitOperations([{name:"animation.set_keyframe",arguments:args}]); }
        catch (error) {
          const status=byId("render-status");
          if(status){status.textContent=error.message;status.className="status error";}
        }
      });
      svg.append(point);
    });
    svg.addEventListener("pointerup", async (event) => {
      if (event.target !== svg && event.target.tagName.toLowerCase() !== "line" &&
          event.target.tagName.toLowerCase() !== "text") return;
      if (event.target.tagName.toLowerCase() === "text") return;
      const rect = svg.getBoundingClientRect();
      const scaleX = width / Math.max(1, rect.width);
      const scaleY = height / Math.max(1, rect.height);
      const x = Math.max(left, Math.min(width-right, (event.clientX-rect.left)*scaleX));
      const y = Math.max(top, Math.min(height-bottom, (event.clientY-rect.top)*scaleY));
      const time = Math.max(0, Math.min(duration, panUs+((x-left)/plotWidth)*visibleDuration));
      const value = maxValue - ((y-top)/plotHeight)*(maxValue-minValue);
      const args={clip_id:clip.id,property,time_us:Math.round(time),
        value:Number(value.toFixed(4)),interpolation:byId("keyframe-interpolation")?.value || "linear"};
      try { await submitOperations([{name:"animation.set_keyframe",arguments:args}]); }
      catch(error) {
        const status=byId("render-status");
        if(status){status.textContent=error.message;status.className="status error";}
      }
    });
    host.append(svg);
    if (!keyframes.length) {
      host.append(element("p","graph-hint","No points yet. Tap the graph to create the first keyframe."));
    }
  }

  function updateInspector() {
    const host = byId("studio-clip-inspector");
    const scope = byId("edit-scope");
    if (!host) return;
    host.replaceChildren();
    document.querySelectorAll(".timeline-clip").forEach((button) => {
      const isSelected = selectedClipIds.has(button.dataset.clipId) || button.dataset.clipId === selectedClipId;
      button.classList.toggle("selected", isSelected);
      button.setAttribute("aria-pressed", isSelected ? "true" : "false");
    });
    const groupButton = byId("studio-group-clips");
    const ungroupButton = byId("studio-ungroup-clips");
    if (groupButton) groupButton.disabled = selectedClipIds.size < 2;
    if (ungroupButton) {
      const grouped = currentProject ? flattenClips(currentProject).some((item) =>
        selectedClipIds.has(item.clip.id) && Boolean(item.clip.group_id)) : false;
      ungroupButton.disabled = !grouped;
    }

    const selected = findSelectedClip();
    const textControlIds = [
      "studio-text-content", "studio-text-family", "studio-text-size",
      "studio-text-fgcolour", "studio-text-olcolour", "studio-text-outline",
      "studio-text-weight", "studio-text-background-fill", "studio-text-bgcolour",
      "studio-text-bgopacity", "studio-text-pad", "studio-text-shadow-color",
      "studio-text-shadow-x", "studio-text-shadow-y", "studio-text-shadow-opacity",
      "studio-text-shadow-blur", "studio-text-letter-spacing", "studio-text-line-spacing",
      "studio-text-halign", "studio-text-valign", "studio-text-x", "studio-text-y",
      "studio-text-width", "studio-text-height", "studio-save-text"
    ];
    textControlIds.forEach((id) => {
      if (byId(id)) byId(id).disabled = !selected || selected.clip.kind !== "text";
    });
    const clipControls = [
      "clip-start-seconds", "clip-speed", "clip-source-in", "clip-source-out", "clip-slip-offset",
      "studio-move-clip", "studio-trim-clip", "studio-slip-clip", "studio-apply-speed", "studio-split-clip",
      "studio-duplicate-clip", "studio-delete-clip", "studio-remove-keyframe",
      "studio-toggle-track-enabled", "studio-toggle-track-muted",
      "studio-copy-keyframes", "studio-paste-keyframes", "studio-apply-motion-preset", "clip-framing",
      "clip-horizontal", "clip-vertical",
      "clip-crop-x", "clip-crop-y", "clip-crop-width", "clip-crop-height",
      "studio-apply-crop", "studio-reset-crop",
      "clip-position-x", "clip-position-y",
      "clip-scale-x", "clip-scale-y", "clip-rotation",
      "clip-opacity", "clip-anchor-x", "clip-anchor-y",
      "clip-flip-horizontal", "clip-flip-vertical",
      "studio-apply-framing", "studio-apply-transform",
      "keyframe-property", "keyframe-value", "keyframe-interpolation",
      "keyframe-time", "studio-add-keyframe"
    ];
    clipControls.forEach((id) => { if (byId(id)) byId(id).disabled = !selected; });
    if (!selected) {
      host.append(element("p", "hint", "Select a clip on the timeline to inspect and edit it."));
      if (scope) scope.textContent = "No clip selected. Your next AI request will apply to the project generally.";
      return;
    }

    const clip = selected.clip;
    const track = selected.track;
    const asset = (currentProject.assets || []).find((item) => item.id === clip.media_id);
    const transform = clip.transform || {};
    const position = transform.position || {};
    const scale = transform.scale || {};
    const details = [
      ["Clip ID", clip.id],
      ["Type", clip.kind],
      ["Track", track.name + " ( " + track.type + " )"],
      ["Start", formatTime(clip.start_us)],
      ["Duration", formatTime(clip.duration_us)],
      ["Source media", asset ? asset.file_name : (clip.media_id || "Text clip")],
      ["Playback speed", clip.playback_rate ? Number(clip.playback_rate).toFixed(2) + "×" : "1.00×"],
      ["Effects", Array.isArray(clip.effects) ? String(clip.effects.length) : "0"],
      ["Keyframes", Array.isArray(clip.keyframes) ? String(clip.keyframes.length) : "0"]
    ];
    if (clip.text && clip.text.content) details.push(["Text", clip.text.content]);
    if (clip.framing) details.push(["Framing", clip.framing.mode]);
    if (clip.crop) details.push(["Manual crop", [
      Math.round(clip.crop.x * 100) + "% left",
      Math.round(clip.crop.y * 100) + "% top",
      Math.round(clip.crop.width * 100) + "% width",
      Math.round(clip.crop.height * 100) + "% height"
    ].join(" · ")]);
    if (transform.flip_horizontal || transform.flip_vertical) {
      details.push(["Flip", [
        transform.flip_horizontal ? "Horizontal" : "",
        transform.flip_vertical ? "Vertical" : ""
      ].filter(Boolean).join(" + ")]);
    }
    if (Number(transform.anchor_x ?? 0.5) !== 0.5 ||
        Number(transform.anchor_y ?? 0.5) !== 0.5) {
      details.push(["Rotation pivot",
        Math.round(Number(transform.anchor_x ?? 0.5) * 100) + "% X · " +
        Math.round(Number(transform.anchor_y ?? 0.5) * 100) + "% Y"]);
    }
    const grid = element("dl", "inspector-grid");
    details.forEach(([label, value]) => {
      grid.append(element("dt", "", label));
      grid.append(element("dd", "", value));
    });
    host.append(grid);

    const setValue = (id, value) => { if (byId(id) && value !== undefined && value !== null) byId(id).value = String(value); };
    setValue("clip-start-seconds", Number(clip.start_us || 0) / 1000000);
    setValue("clip-speed", Number(clip.playback_rate || 1));
    setValue("clip-source-in", Number(clip.source_in_us || 0) / 1000000);
    setValue("clip-source-out", Number(clip.source_out_us ??
      (Number(clip.source_in_us || 0) + Number(clip.duration_us || 0) * Number(clip.playback_rate || 1))) / 1000000);
    setValue("clip-framing", clip.framing?.mode || "none");
    setValue("clip-horizontal", clip.framing?.horizontal_alignment || "center");
    setValue("clip-vertical", clip.framing?.vertical_alignment || "middle");
    setValue("clip-crop-x", Number(clip.crop?.x ?? 0) * 100);
    setValue("clip-crop-y", Number(clip.crop?.y ?? 0) * 100);
    setValue("clip-crop-width", Number(clip.crop?.width ?? 1) * 100);
    setValue("clip-crop-height", Number(clip.crop?.height ?? 1) * 100);
    setValue("clip-position-x", Number(position.x ?? 0));
    setValue("clip-position-y", Number(position.y ?? 0));
    setValue("clip-scale-x", Number(scale.x ?? 1));
    setValue("clip-scale-y", Number(scale.y ?? 1));
    setValue("clip-rotation", Number(transform.rotation_deg ?? 0));
    setValue("clip-opacity", Number(transform.opacity ?? 1));
    setValue("clip-anchor-x", Number(transform.anchor_x ?? 0.5) * 100);
    setValue("clip-anchor-y", Number(transform.anchor_y ?? 0.5) * 100);
    const textData = clip.text || {};
    setValue("studio-text-content", textData.content || "");
    setValue("studio-text-family", textData.family || "Sans");
    setValue("studio-text-size", textData.size ?? 48);
    setValue("studio-text-fgcolour", textData.fgcolour || "#FFFFFF");
    setValue("studio-text-olcolour", textData.olcolour || "#000000");
    setValue("studio-text-outline", textData.outline ?? 1);
    setValue("studio-text-weight", textData.weight ?? 400);
    if (byId("studio-text-background-fill")) byId("studio-text-background-fill").checked = Boolean(textData.background_fill);
    setValue("studio-text-bgcolour", textData.bgcolour || "#000000");
    setValue("studio-text-bgopacity", textData.bgopacity ?? 0.45);
    setValue("studio-text-pad", textData.pad ?? 12);
    setValue("studio-text-shadow-color", textData.shadow_color || "#000000");
    setValue("studio-text-shadow-x", textData.shadow_x ?? 0);
    setValue("studio-text-shadow-y", textData.shadow_y ?? 0);
    setValue("studio-text-shadow-opacity", textData.shadow_opacity ?? 0.7);
    setValue("studio-text-shadow-blur", textData.shadow_blur ?? 0);
    setValue("studio-text-letter-spacing", textData.letter_spacing_px ?? 0);
    setValue("studio-text-line-spacing", textData.line_spacing_px ?? 0);
    setValue("studio-text-halign", textData.halign || textData.align || "center");
    setValue("studio-text-valign", textData.valign || "middle");
    setValue("studio-text-x", textData.x_percent ?? 5);
    setValue("studio-text-y", textData.y_percent ?? 68);
    setValue("studio-text-width", textData.width_percent ?? 90);
    setValue("studio-text-height", textData.height_percent ?? 25);
    if (byId("clip-flip-horizontal")) byId("clip-flip-horizontal").checked = Boolean(transform.flip_horizontal);
    if (byId("clip-flip-vertical")) byId("clip-flip-vertical").checked = Boolean(transform.flip_vertical);
    const keyframeTime = Math.max(0, playheadUs - Number(clip.start_us || 0));
    setValue("keyframe-time", keyframeTime / 1000000);
    const setDisabled = (id, value) => { if (byId(id)) byId(id).disabled = value; };
    const visual = ["video", "image"].includes(clip.kind);
    const keyframeProperty = byId("keyframe-property");
    if (keyframeProperty) {
      Array.from(keyframeProperty.options).forEach((option) => {
        option.disabled = clip.kind === "text" && option.value !== "opacity";
      });
      if (clip.kind === "text") keyframeProperty.value = "opacity";
    }
    ["clip-crop-x", "clip-crop-y", "clip-crop-width", "clip-crop-height",
      "studio-apply-crop", "studio-reset-crop"].forEach((id) => setDisabled(id, !visual));
    setDisabled("clip-framing", !visual);
    setDisabled("clip-horizontal", !visual);
    ["clip-position-x","clip-position-y","clip-scale-x","clip-scale-y","clip-rotation","clip-opacity","studio-apply-transform"]
      .forEach((id) => setDisabled(id, !visual));
    setDisabled("clip-speed", !["video","audio"].includes(clip.kind));
    setDisabled("studio-slip-clip", !["video","audio"].includes(clip.kind));
    ["clip-source-in","clip-source-out","studio-trim-clip"].forEach((id) =>
      setDisabled(id, clip.kind === "text"));
    if (byId("studio-delete-clip")) byId("studio-delete-clip").textContent = "Delete clip";
    if (scope) {
      scope.textContent = "Selected clip: " + clip.id +
        ". AI requests will include this clip as the intended target. Direct controls apply registered operations to this clip.";
    }
    renderKeyframeGraph();
  }

  function renderTimeline() {
    if (!currentProject) return;
    const canvas = byId("timeline-canvas");
    const ruler = byId("timeline-ruler");
    const trackHost = byId("timeline-tracks");
    const empty = byId("studio-timeline-empty");
    if (!canvas || !ruler || !trackHost) return;

    const tracks = (Array.isArray(currentProject.tracks) ? currentProject.tracks : [])
      .slice().sort((a, b) => Number(a.order || 0) - Number(b.order || 0));
    const entries = flattenClips(currentProject);
    const endUs = entries.reduce((end, item) => Math.max(
      end,
      Number(item.clip.start_us || 0) + Number(item.clip.duration_us || 0)
    ), 0);
    const durationSeconds = Math.max(5, endUs / 1000000);
    const zoomInput = byId("timeline-zoom");
    const zoom = zoomInput ? Math.max(50, Math.min(200, Number(zoomInput.value || 100))) : 100;
    timelinePixelsPerSecond = 46 * zoom / 100;
    const pixelsPerSecond = timelinePixelsPerSecond;
    const laneWidth = Math.min(12000, Math.max(680, Math.ceil(durationSeconds * pixelsPerSecond)));
    const labelWidth = 104;

    canvas.style.width = (labelWidth + laneWidth + 12) + "px";
    canvas.style.setProperty("--lane-width", laneWidth + "px");
    ruler.replaceChildren();
    trackHost.replaceChildren();

    const rulerLabel = element("div", "timeline-label-cell", "TIME");
    const rulerLane = element("div", "timeline-ruler-lane");
    const step = durationSeconds > 900 ? 60 : durationSeconds > 240 ? 30 : durationSeconds > 60 ? 10 : 5;
    for (let second = 0; second <= durationSeconds; second += step) {
      const tick = element("span", "timeline-tick", formatTime(second * 1000000));
      tick.style.left = (second * pixelsPerSecond) + "px";
      rulerLane.append(tick);
    }
    const rulerPlayhead = element("span", "timeline-playhead");
    rulerPlayhead.setAttribute("aria-hidden", "true");
    rulerLane.append(rulerPlayhead);
    (currentProject.markers || []).forEach((marker) => {
      const pin = element("button", "timeline-marker", marker.label || "Marker");
      pin.type = "button";
      pin.title = (marker.label || "Marker") + " · " + formatTime(marker.time_us);
      pin.style.left = (Number(marker.time_us || 0) / 1000000 * pixelsPerSecond) + "px";
      pin.style.borderColor = marker.colour || "#F5C542";
      pin.addEventListener("click", () => setPlayhead(Number(marker.time_us || 0)));
      rulerLane.append(pin);
    });
    ruler.append(rulerLabel, rulerLane);
    const markerList = byId("studio-marker-list");
    if (markerList) {
      markerList.replaceChildren();
      (currentProject.markers || []).forEach((marker) => {
        const item = element("div", "marker-chip");
        const jump = element("button", "btn secondary", (marker.label || "Marker") + " · " + formatTime(marker.time_us));
        jump.type = "button";
        jump.addEventListener("click", () => setPlayhead(Number(marker.time_us || 0)));
        const move = element("button", "btn secondary", "Move to playhead");
        move.type = "button";
        move.addEventListener("click", () => submitOperations([{
          name: "timeline.move_marker",
          arguments: {marker_id: marker.id, time_us: Math.max(0, Math.round(playheadUs))}
        }]).catch((error) => {
          const status = byId("render-status");
          if (status) { status.textContent = error.message; status.className = "status error"; }
        }));
        const remove = element("button", "btn secondary", "Remove");
        remove.type = "button";
        remove.addEventListener("click", () => submitOperations([{name:"timeline.remove_marker",arguments:{marker_id:marker.id}}]).catch((error) => {
          const status = byId("render-status");
          if (status) { status.textContent = error.message; status.className = "status error"; }
        }));
        item.append(jump, move, remove); markerList.append(item);
      });
    }

    tracks.forEach((track) => {
      const row = element("div", "timeline-track-row");
      row.dataset.trackId = track.id;
      const label = element("div", "timeline-label-cell track-label");
      label.append(
        element("strong", "", track.name || "Untitled track"),
        element("span", "track-type", String(track.type || "track").toUpperCase() +
          (track.locked ? " · LOCKED" : ""))
      );
      const lane = element("div", "timeline-lane");
      lane.dataset.trackId = track.id;
      lane.style.backgroundSize = pixelsPerSecond + "px 100%";
      lane.addEventListener("pointerdown", (event) => {
        if (event.target.closest(".timeline-clip")) return;
        const rect = lane.getBoundingClientRect();
        const localX = Math.max(0, event.clientX - rect.left);
        setPlayhead(Math.round(localX / pixelsPerSecond * 1000000));
      });
      (track.clips || []).slice().sort((a, b) => Number(a.start_us || 0) - Number(b.start_us || 0))
        .forEach((clip) => {
          const asset = (currentProject.assets || []).find((item) => item.id === clip.media_id);
          const labelText = clip.kind === "text"
            ? ((clip.text && clip.text.content) || "Text clip")
            : ((asset && asset.file_name) || clip.kind || "Clip");
          const button = element("button", "timeline-clip kind-" + String(clip.kind || "video"),
            String(labelText).slice(0, 32));
          button.type = "button";
          button.dataset.clipId = clip.id;
          button.title = labelText + " · " + formatTime(clip.start_us) + " · " + formatTime(clip.duration_us);
          button.setAttribute("aria-label", "Select " + clip.kind + " clip " + labelText +
            ". Drag the body to move or the edges to trim.");
          button.setAttribute("aria-pressed", clip.id === selectedClipId ? "true" : "false");
          const left = Math.max(0, Number(clip.start_us || 0) / 1000000 * pixelsPerSecond);
          const width = Math.max(38, Number(clip.duration_us || 0) / 1000000 * pixelsPerSecond);
          button.style.left = left + "px";
          button.style.width = Math.max(0, Math.min(width, laneWidth - left)) + "px";
          if (selectedClipIds.has(clip.id) || clip.id === selectedClipId) button.classList.add("selected");
          if (clip.kind !== "text") {
            const leftHandle = element("span", "clip-handle clip-handle-left");
            const rightHandle = element("span", "clip-handle clip-handle-right");
            leftHandle.setAttribute("aria-hidden", "true");
            rightHandle.setAttribute("aria-hidden", "true");
            button.append(leftHandle, rightHandle);
          }
          button.addEventListener("click", (event) => {
            if (Date.now() < skipClipClickUntil) return;
            if (event.shiftKey) {
              if (selectedClipIds.has(clip.id)) selectedClipIds.delete(clip.id);
              else selectedClipIds.add(clip.id);
              selectedClipId = selectedClipIds.has(clip.id)
                ? clip.id : ([...selectedClipIds].pop() || "");
              if (!selectedClipIds.size) {
                selectedClipIds.add(clip.id);
                selectedClipId = clip.id;
              }
            } else {
              selectedClipIds = new Set([clip.id]);
              selectedClipId = clip.id;
            }
            updateInspector();
            renderMediaBin();
          });
          bindClipDrag(button, clip, track, lane);
          lane.append(button);
        });
      const playheadLine = element("span", "timeline-playhead");
      playheadLine.setAttribute("aria-hidden", "true");
      lane.append(playheadLine);
      if (!(track.clips || []).length) lane.append(element("span", "lane-empty", "Empty track"));
      row.append(label, lane);
      trackHost.append(row);
    });

    if (empty) {
      empty.textContent = entries.length
        ? tracks.length + " track(s) · " + entries.length + " clip(s)"
        : "This project has no timeline clips yet.";
    }
    const durationLabel = byId("studio-duration");
    if (durationLabel) durationLabel.textContent = "Timeline length " + formatTime(endUs);
    const seek = byId("timeline-seek");
    if (seek) seek.max = String(Math.max(1000000, endUs));
    fillTrackSelector();
    const subtitleTrack = byId("studio-subtitle-track");
    if (subtitleTrack) {
      const prior = subtitleTrack.value;
      subtitleTrack.replaceChildren();
      (currentProject.tracks || []).filter((track) => track.type === "text" && track.locked !== true)
        .sort((a,b) => Number(a.order || 0) - Number(b.order || 0)).forEach((track) => {
          const option = element("option", "", track.name || "Text track");
          option.value = track.id;
          subtitleTrack.append(option);
        });
      if ([...subtitleTrack.options].some((option) => option.value === prior)) subtitleTrack.value = prior;
      subtitleTrack.disabled = subtitleTrack.options.length === 0;
    }
    const profile = currentProject.video_profile || {};
    const frameRate = profile.frame_rate || {};
    const setValue = (id, value) => { if (byId(id) && value !== undefined) byId(id).value = String(value); };
    setValue("profile-width", profile.width);
    setValue("profile-height", profile.height);
    setValue("profile-fps-num", frameRate.numerator);
    setValue("profile-fps-den", frameRate.denominator);
    const stage=byId("studio-preview-stage");
    if(stage && profile.width && profile.height) stage.style.aspectRatio=String(profile.width)+" / "+String(profile.height);
    setPlayhead(playheadUs, false);
    updateInspector();
    renderKeyframeGraph();
  }

  function renderMediaBin() {
    const host = byId("studio-media-bin");
    if (!host || !currentProject) return;
    host.replaceChildren();
    const assets = Array.isArray(currentProject.assets) ? currentProject.assets : [];
    const query = String(byId("media-bin-search")?.value || "").trim().toLowerCase();
    const folderFilter = byId("media-bin-folder-filter");
    const previousFolder = folderFilter?.value || "";
    if (folderFilter) {
      const folders = [...new Set(assets.map((asset) => asset.folder || "Unsorted"))].sort();
      folderFilter.replaceChildren();
      const all = document.createElement("option");
      all.value = ""; all.textContent = "All folders";
      folderFilter.append(all);
      folders.forEach((folder) => {
        const option = document.createElement("option");
        option.value = folder; option.textContent = folder;
        folderFilter.append(option);
      });
      if (folders.includes(previousFolder)) folderFilter.value = previousFolder;
    }
    const activeFolder = folderFilter?.value || "";
    const filtered = assets.filter((asset) => {
      const folder = asset.folder || "Unsorted";
      const tags = Array.isArray(asset.tags) ? asset.tags : [];
      const matchesQuery = !query ||
        String(asset.file_name || "").toLowerCase().includes(query) ||
        String(asset.media_type || "").toLowerCase().includes(query) ||
        folder.toLowerCase().includes(query) ||
        tags.some((tag) => String(tag).toLowerCase().includes(query));
      return matchesQuery && (!activeFolder || folder === activeFolder);
    });
    if (!filtered.length) {
      host.append(element("p", "hint", assets.length
        ? "No project media matches these filters."
        : "No media assets are listed in this project."));
      return;
    }
    filtered.forEach((asset) => {
      const used = flattenClips(currentProject).filter((item) => item.clip.media_id === asset.id).length;
      const existingProxy = assets.find((item) => item.proxy_for_media_id === asset.id);
      const proxyStatus = asset.proxy_for_media_id
        ? element("p", "hint", "Low-resolution proxy for " + asset.proxy_for_media_id)
        : existingProxy
          ? element("p", "hint", "Proxy ready · " + existingProxy.file_name)
          : null;
      const proxyButton = asset.media_type === "video" && !asset.proxy_for_media_id && !existingProxy
        ? element("button", "btn secondary", "Create 640×360 proxy")
        : null;
      if (proxyButton) {
        proxyButton.type = "button";
        proxyButton.addEventListener("click", async () => {
          proxyButton.disabled = true;
          proxyButton.textContent = "Generating proxy…";
          try {
            await submitOperations([{name:"media.create_proxy",arguments:{media_id:asset.id}}]);
          } catch (error) {
            const status = byId("render-status");
            if (status) { status.textContent = error.message; status.className = "status error"; }
            proxyButton.disabled = false;
            proxyButton.textContent = "Create 640×360 proxy";
          }
        });
      }
      const card = element("article", "media-bin-item");
      const title = element("strong", "", asset.file_name || asset.id || "Media asset");
      const preview = element("div", "media-preview");
      if (asset.thumbnail_data_url) {
        const image = element("img", "media-thumbnail");
        image.src = asset.thumbnail_data_url;
        image.alt = "Preview of " + (asset.file_name || "media asset");
        image.loading = "lazy";
        preview.append(image);
      } else {
        preview.append(element("span", "media-thumbnail-placeholder", String(asset.media_type || "MEDIA").toUpperCase() + " · preview unavailable"));
      }
      if (asset.waveform && Array.isArray(asset.waveform.samples)) {
        const waveform = element("div", "media-waveform");
        waveform.setAttribute("aria-label", "Audio waveform preview");
        asset.waveform.samples.forEach((peak) => {
          const bar = element("span", "media-waveform-bar");
          bar.style.height = Math.max(3, Math.round(Number(peak) * 28)) + "px";
          waveform.append(bar);
        });
        preview.append(waveform);
      }
      const tags = Array.isArray(asset.tags) ? asset.tags : [];
      const meta = element("p", "hint", [
        String(asset.media_type || "media").toUpperCase(),
        asset.duration_us ? formatTime(asset.duration_us) : "Duration n/a",
        formatBytes(asset.size_bytes),
        "Folder: " + (asset.folder || "Unsorted"),
        tags.length ? "Tags: " + tags.join(", ") : "No tags",
        used + (used === 1 ? " timeline use" : " timeline uses")
      ].join(" · "));
      const editor = element("div", "media-organize-controls");
      const folderLabel = element("label", "", "Folder");
      const folderInput = document.createElement("input");
      folderInput.type = "text";
      folderInput.maxLength = 64;
      folderInput.value = asset.folder || "Unsorted";
      folderInput.setAttribute("aria-label", "Folder for " + (asset.file_name || asset.id));
      folderLabel.append(folderInput);
      const tagsLabel = element("label", "", "Tags (comma separated)");
      const tagsInput = document.createElement("input");
      tagsInput.type = "text";
      tagsInput.maxLength = 400;
      tagsInput.value = tags.join(", ");
      tagsInput.setAttribute("aria-label", "Tags for " + (asset.file_name || asset.id));
      tagsLabel.append(tagsInput);
      const saveOrganization = element("button", "btn secondary", "Save folder and tags");
      saveOrganization.type = "button";
      saveOrganization.addEventListener("click", async () => {
        const folder = folderInput.value.trim() || "Unsorted";
        if (folder.length > 64 || /[\\/]/.test(folder) || folder === "." || folder === "..") {
          const status = byId("render-status");
          if (status) { status.textContent = "Use a simple folder name up to 64 characters."; status.className = "status error"; }
          return;
        }
        const nextTags = tagsInput.value.split(",").map((tag) => tag.trim()).filter(Boolean);
        if (nextTags.length > 12 || nextTags.some((tag) => tag.length > 32) ||
            new Set(nextTags.map((tag) => tag.toLowerCase())).size !== nextTags.length) {
          const status = byId("render-status");
          if (status) { status.textContent = "Use up to 12 unique tags, each no longer than 32 characters."; status.className = "status error"; }
          return;
        }
        try {
          await submitOperations([{name:"media.organize_asset",arguments:{
            media_id:asset.id,folder,tags:nextTags
          }}]);
        } catch (error) {
          const status = byId("render-status");
          if (status) { status.textContent = error.message; status.className = "status error"; }
        }
      });
      editor.append(folderLabel, tagsLabel, saveOrganization);
      const replace = element("button", "btn secondary", "Replace selected clip source");
      replace.type = "button";
      const target = findSelectedClip();
      replace.disabled = !target || target.track.locked === true ||
        target.clip.kind !== asset.media_type;
      replace.title = !target
        ? "Select a clip on the timeline first."
        : target.track.locked
          ? "Unlock the selected clip's track before replacing its source."
          : target.clip.kind !== asset.media_type
            ? "Choose an asset with the same media type as the selected clip."
            : "Replace the selected clip's source while preserving its timeline position and supported properties.";
      replace.addEventListener("click", async () => {
        try {
          const selected = findSelectedClip();
          if (!selected) throw new Error("Select a clip on the timeline first.");
          if (selected.track.locked) throw new Error("Unlock the selected clip's track before replacing its source.");
          if (selected.clip.kind !== asset.media_type) {
            throw new Error("Choose an asset with the same media type as the selected clip.");
          }
          await submitOperations([{name:"timeline.replace_clip_media",arguments:{
            clip_id:selected.clip.id,media_id:asset.id
          }}]);
        } catch (error) {
          const status = byId("render-status");
          if (status) { status.textContent = error.message; status.className = "status error"; }
        }
      });
      const overwrite = element("button", "btn secondary", "Replace & ripple");
      overwrite.type = "button";
      overwrite.disabled = !target || target.track.locked === true || target.clip.kind !== asset.media_type;
      overwrite.title = overwrite.disabled
        ? "Select an unlocked clip and a same-type media asset."
        : "Replace the selected clip and shift later clips by the duration difference.";
      overwrite.addEventListener("click", async () => {
        try {
          const selected = findSelectedClip();
          if (!selected) throw new Error("Select a clip on the timeline first.");
          if (selected.track.locked || selected.clip.kind !== asset.media_type) {
            throw new Error("Choose an unlocked clip and same-type replacement media.");
          }
          const args = {clip_id:selected.clip.id,media_id:asset.id};
          if (Number.isSafeInteger(Number(asset.duration_us)) && Number(asset.duration_us) > 0) {
            args.duration_us = Number(asset.duration_us);
          }
          await submitOperations([{name:"timeline.ripple_overwrite_clip",arguments:args}]);
        } catch (error) {
          const status = byId("render-status");
          if (status) { status.textContent = error.message; status.className = "status error"; }
        }
      });
      const insert = element("button", "btn secondary", "Insert & ripple");
      insert.type = "button";
      const compatibleTypes = asset.media_type === "audio"
        ? ["audio"]
        : asset.media_type === "image"
          ? ["overlay"]
          : asset.media_type === "video"
            ? ["video", "overlay"] : [];
      const orderedTracks = (currentProject.tracks || []).slice()
        .sort((a, b) => Number(a.order || 0) - Number(b.order || 0));
      const activeTrackId = byId("manage-track")?.value || "";
      const activeTrack = orderedTracks.find((track) => track.id === activeTrackId);
      const targetTrack = activeTrack &&
        compatibleTypes.includes(activeTrack.type) &&
        activeTrack.locked !== true && activeTrack.enabled !== false
          ? activeTrack
          : orderedTracks.find((track) =>
              compatibleTypes.includes(track.type) &&
              track.locked !== true && track.enabled !== false);
      const insertDurationUs = asset.media_type === "image"
        ? 5000000 : Number(asset.duration_us || 0);
      insert.disabled = !targetTrack || !Number.isSafeInteger(insertDurationUs) || insertDurationUs < 1;
      insert.title = !targetTrack
        ? "Add an unlocked compatible track before ripple insertion."
        : !Number.isSafeInteger(insertDurationUs) || insertDurationUs < 1
          ? "This media asset needs a verified duration before it can be inserted."
          : "Insert at the playhead and shift later clips on the selected track forward.";
      insert.addEventListener("click", async () => {
        try {
          if (!targetTrack) throw new Error("Add an unlocked compatible track first.");
          if (!Number.isSafeInteger(insertDurationUs) || insertDurationUs < 1) {
            throw new Error("This media asset has no verified duration.");
          }
          const args = {
            track_id:targetTrack.id,
            ripple_track_ids:orderedTracks.filter((track) => track.locked !== true).map((track) => track.id),
            kind:asset.media_type,
            media_id:asset.id,
            start_us:Math.max(0, Math.round(playheadUs)),
            duration_us:insertDurationUs,
            source_in_us:0,
            playback_rate:1
          };
          if (asset.media_type !== "image") args.source_out_us=insertDurationUs;
          await submitOperations([{name:"timeline.ripple_insert_clip",arguments:args}]);
        } catch (error) {
          const status = byId("render-status");
          if (status) { status.textContent = error.message; status.className = "status error"; }
        }
      });
      const relinkInput = document.createElement("input");
      relinkInput.type = "file";
      relinkInput.hidden = true;
      relinkInput.accept = asset.media_type === "video" ? "video/*" :
        asset.media_type === "audio" ? "audio/*" : "image/*";
      const relink = element("button", "btn secondary", "Relink missing file");
      relink.type = "button";
      relink.addEventListener("click", () => relinkInput.click());
      relinkInput.addEventListener("change", async () => {
        const file = relinkInput.files && relinkInput.files[0];
        if (!file) return;
        try {
          const extension = (file.name.split(".").pop() || "").toLowerCase();
          const supported = asset.media_type === "video"
            ? ["mp4","mov","m4v","webm","mkv"]
            : asset.media_type === "audio"
              ? ["mp3","wav","m4a","aac","ogg","flac"]
              : ["jpg","jpeg","png","webp","gif"];
          if (!supported.includes(extension)) throw new Error("Choose a supported " + asset.media_type + " file.");
          if (file.size < 1 || file.size > 50 * 1024 * 1024) throw new Error("The replacement must be 1 byte to 50 MB.");
          const jobId = window.getActiveStudioJobId();
          const projectResponse = await window.api("/api/v1/jobs/" + jobId + "/project");
          const headers = {
            "Content-Type":file.type || "application/octet-stream",
            "X-File-Name":encodeURIComponent(file.name),
            "X-File-Size":String(file.size),
            "X-Media-Type":asset.media_type,
            "X-Expected-Revision":String(projectResponse.revision)
          };
          if (asset.media_type !== "image") {
            const duration = await window.readBrowserMediaDuration(file, asset.media_type);
            headers["X-Media-Duration-Us"] = String(duration);
          }
          const relinkResult = await window.api("/api/v1/jobs/" + jobId + "/assets/" + encodeURIComponent(asset.id) + "/relink", {
            method:"PUT", headers, body:file
          });
          let previewWarning = "";
          try {
            const preview = await window.createMediaPreview(file, asset.media_type);
            if (Object.keys(preview).length) {
              await window.api("/api/v1/jobs/" + jobId + "/assets/" + encodeURIComponent(asset.id) + "/preview", {
                method:"POST", headers:{"Content-Type":"application/json"},
                body:JSON.stringify({expected_revision:relinkResult.project_revision,...preview})
              });
            }
          } catch (previewError) { previewWarning = " Preview regeneration was unavailable."; }
          await window.loadProject(false);
          const status = byId("render-status");
          if (status) { status.textContent = "Media file relinked. Existing clip references were preserved." + previewWarning; status.className = previewWarning ? "status error" : "status success"; }
        } catch (error) {
          const status = byId("render-status");
          if (status) { status.textContent = error.message; status.className = "status error"; }
        } finally { relinkInput.value = ""; }
      });
      const place = element("button", "btn secondary", "Place at playhead");
      place.type = "button";
      place.addEventListener("click", async () => {
        try {
          if (typeof window.studioAddMediaAtPlayhead !== "function") {
            throw new Error("Timeline media placement is not ready.");
          }
          await window.studioAddMediaAtPlayhead(asset.id);
        } catch (error) {
          const status = byId("render-status");
          if (status) { status.textContent = error.message; status.className = "status error"; }
        }
      });
      if (proxyStatus) card.append(proxyStatus);
      card.append(title, preview, meta, editor, replace, overwrite, insert, relinkInput, relink, place);
      if (proxyButton) card.append(proxyButton);
      host.append(card);
    });
  }

  async function addMediaAtPlayhead(mediaId) {
    const asset = (currentProject?.assets || []).find((item) => item.id === mediaId);
    if (!asset) throw new Error("The selected media is not in this project.");
    const kind = asset.media_type;
    if (!["video","image","audio"].includes(kind)) throw new Error("This asset type cannot be placed on the timeline.");
    const preferredTypes = kind === "audio" ? ["audio"] : ["overlay","video"];
    const tracks = (currentProject.tracks || []).slice().sort((a,b)=>Number(a.order||0)-Number(b.order||0));
    let track = null;
    for (const type of preferredTypes) {
      track = tracks.find((item)=>item.type===type && item.locked!==true && item.enabled!==false);
      if (track) break;
    }
    if (!track) {
      throw new Error(kind==="audio"
        ? "Add an audio track before placing this media."
        : "Add an overlay or video track before placing this media.");
    }
    const durationUs = Number(asset.duration_us || (kind==="image" ? 5000000 : 0));
    if (!Number.isSafeInteger(durationUs) || durationUs<1) {
      throw new Error("This media has no verified duration yet. Re-import it or inspect the source before placing it.");
    }
    const args={
      track_id:track.id,kind,media_id:asset.id,
      start_us:Math.max(0,Math.round(playheadUs)),duration_us:durationUs,
      source_in_us:0,playback_rate:1
    };
    if (kind!=="image") args.source_out_us=durationUs;
    return submitOperations([{name:"timeline.add_clip",arguments:args}]);
  }
  window.studioAddMediaAtPlayhead = addMediaAtPlayhead;

  function setView(view) {
    activeView = view === "media" ? "media" : "timeline";
    const timeline = byId("studio-timeline-view");
    const media = byId("studio-media-view");
    const timelineTab = byId("studio-tab-timeline");
    const mediaTab = byId("studio-tab-media");
    if (timeline) timeline.classList.toggle("hidden", activeView !== "timeline");
    if (media) media.classList.toggle("hidden", activeView !== "media");
    if (timelineTab) timelineTab.setAttribute("aria-pressed", activeView === "timeline" ? "true" : "false");
    if (mediaTab) mediaTab.setAttribute("aria-pressed", activeView === "media" ? "true" : "false");
  }

  function renderProject(project, revision) {
    if (!project || typeof project !== "object" || !Array.isArray(project.tracks)) return;
    currentProject = project;
    currentRevision = revision || project.revision || 1;
    const liveIds = new Set(flattenClips(project).map(({clip}) => clip.id));
    selectedClipIds = new Set([...selectedClipIds].filter((id) => liveIds.has(id)));
    if (!liveIds.has(selectedClipId)) selectedClipId = "";
    if (!selectedClipId && selectedClipIds.size) selectedClipId = [...selectedClipIds][0];
    const meta = byId("studio-project-meta");
    if (meta) {
      const profile = project.video_profile || {};
      const frameRate = profile.frame_rate || {};
      const fps = frameRate.numerator && frameRate.denominator
        ? (Number(frameRate.numerator) / Number(frameRate.denominator)).toFixed(2) + " fps"
        : "frame rate unavailable";
      meta.textContent = (project.name || "Untitled project") + " · Revision " + currentRevision +
        " · " + (profile.width || "?") + "×" + (profile.height || "?") + " · " + fps;
    }
    const editor = byId("studio-editor");
    if (editor) editor.classList.remove("hidden");
    renderTimeline();
    renderMediaBin();
    renderSilenceTranscriptSelector();
    setView(activeView);
  }

  function renderSilenceTranscriptSelector() {
    const select = byId("studio-silence-transcript");
    const reviewButton = byId("studio-review-silence");
    if (!select || !currentProject) return;
    const previous = select.value;
    const transcripts = Array.isArray(currentProject.transcripts) ? currentProject.transcripts : [];
    select.replaceChildren();
    if (!transcripts.length) {
      const option = element("option", "", "No timed transcript loaded");
      option.value = "";
      select.append(option);
      select.disabled = true;
      if (reviewButton) reviewButton.disabled = true;
      return;
    }
    transcripts.forEach((transcript) => {
      const option = element(
        "option", "",
        (transcript.name || "Transcript") +
          (transcript.language ? " · " + transcript.language : "") +
          " · " + (transcript.words || []).length + " words"
      );
      option.value = transcript.id;
      select.append(option);
    });
    if (transcripts.some((item) => item.id === previous)) select.value = previous;
    select.disabled = false;
    if (reviewButton) reviewButton.disabled = false;
  }

  function handleStudioAnalysisResult(analysisResult) {
    const payload = (analysisResult?.results || []).find(
      (item) => item.name === "transcript.review_silence"
    )?.result;
    if (!payload) return;
    const status = byId("studio-silence-status");
    const host = byId("studio-silence-candidates");
    if (!host || !status) return;
    host.replaceChildren();
    const coverage = Number(payload.analysis_coverage_seconds || 0).toFixed(1);
    status.textContent = payload.measurement_status === "measured"
      ? payload.candidate_count + " measured candidate(s). Scanned " + coverage +
        " seconds" + (payload.full_duration_scanned ? " (full source)." : " (partial scan).")
      : "Silence review unavailable: " + String(payload.measurement_status || "unknown") + ".";
    (payload.limitations || []).forEach((limitation) => {
      host.append(element("p", "hint", limitation));
    });
    if (!payload.candidates?.length) {
      host.append(element("p", "hint", "No measured silence gaps between adjacent transcript words met the selected minimum duration."));
      return;
    }
    payload.candidates.forEach((candidate) => {
      const card = element("article", "silence-candidate");
      const heading = element("strong", "", "Measured gap · " +
        formatTime(candidate.source_start_us) + "–" + formatTime(candidate.source_end_us));
      const detail = element("p", "hint",
        "Between “" + candidate.adjacent_words.before + "” and “" +
        candidate.adjacent_words.after + "” · " +
        (Number(candidate.measured_duration_us || 0) / 1000).toFixed(0) + " ms · timeline " +
        formatTime(candidate.timeline_cut_start_us) + "–" +
        formatTime(candidate.timeline_cut_end_us));
      const assessment = element("p", "hint",
        "Semantic assessment: " + String(candidate.semantic_assessment || "not_evaluated") +
        ". This does not decide whether the pause is unwanted.");
      card.append(heading, detail, assessment);
      if (candidate.blockers?.length) {
        card.append(element("p", "hint", "Cannot apply: " + candidate.blockers.join(", ")));
      }
      const approve = element("button", "btn secondary",
        candidate.can_apply ? "Approve and apply this cut" : "Cut unavailable");
      approve.type = "button";
      approve.disabled = !candidate.can_apply;
      approve.addEventListener("click", async () => {
        const seconds = Number(payload.analysis_seconds || 600);
        const threshold = Number(payload.silence_threshold_db ?? -50);
        const minimumUs = Number(payload.minimum_silence_us || 100000);
        const question = "Remove only the measured " +
          (Number(candidate.measured_duration_us || 0) / 1000).toFixed(0) +
          " ms silence between “" + candidate.adjacent_words.before + "” and “" +
          candidate.adjacent_words.after + "”?";
        if (!window.confirm(question)) return;
        approve.disabled = true;
        try {
          await submitOperations([{
            name: "transcript.apply_silence_cut",
            arguments: {
              transcript_id: payload.transcript_id,
              clip_id: payload.clip_id,
              source_start_us: candidate.source_start_us,
              source_end_us: candidate.source_end_us,
              analysis_seconds: seconds,
              silence_threshold_db: threshold,
              minimum_silence_us: minimumUs
            }
          }], ["transcript.apply_silence_cut"]);
          status.textContent = "Approved cut queued. The edited project will be saved and rendered.";
          host.replaceChildren();
        } catch (error) {
          status.textContent = error.message;
          approve.disabled = false;
        }
      });
      card.append(approve);
      host.append(card);
    });
  }

  window.handleStudioAnalysisResult = handleStudioAnalysisResult;

  function selectedClipInstruction() {
    const selected = findSelectedClip();
    if (!selected) return "";
    const clip = selected.clip;
    return "Target clip context: clip_id=" + clip.id +
      ", track=" + selected.track.name +
      ", kind=" + clip.kind +
      ", start=" + formatTime(clip.start_us) +
      ", duration=" + formatTime(clip.duration_us) +
      ". Treat this clip as the intended target; do not change other clips unless the user's request requires it.\n";
  }

  window.renderStudioProject = renderProject;
  window.studioSelectedClipInstruction = selectedClipInstruction;
  window.getStudioPreviewMediaId = () => {
    const selected = findSelectedClip();
    return selected && selected.clip.kind === "video"
      ? selected.clip.media_id : "source-video";
  };

  const zoomInput = byId("timeline-zoom");
  if (zoomInput) zoomInput.addEventListener("input", renderTimeline);
  const mediaSearch=byId("media-bin-search");
  if(mediaSearch)mediaSearch.addEventListener("input",renderMediaBin);
  const mediaFolderFilter=byId("media-bin-folder-filter");
  if(mediaFolderFilter)mediaFolderFilter.addEventListener("change",renderMediaBin);
  const seek = byId("timeline-seek");
  if (seek) seek.addEventListener("input", () => setPlayhead(Number(seek.value)));
  const graphProperty = byId("keyframe-property");
  if (graphProperty) graphProperty.addEventListener("change", renderKeyframeGraph);
  const graphZoom = byId("keyframe-graph-zoom");
  if (graphZoom) graphZoom.addEventListener("input", renderKeyframeGraph);
  const graphPan = byId("keyframe-graph-pan");
  if (graphPan) graphPan.addEventListener("input", renderKeyframeGraph);
  const graphReset = byId("keyframe-graph-reset");
  if (graphReset) graphReset.addEventListener("click", () => {
    if (graphZoom) graphZoom.value = "100";
    if (graphPan) graphPan.value = "0";
    renderKeyframeGraph();
  });
  const preview = byId("studio-preview");
  if (preview) preview.addEventListener("timeupdate", () => {
    if (!currentProject || !Number.isFinite(preview.currentTime)) return;
    const previewMediaId = preview.dataset.mediaId || "source-video";
    const main = flattenClips(currentProject).find(({clip}) =>
      clip.kind === "video" && clip.media_id === previewMediaId);
    const mapped = preview.dataset.previewMode === "composite"
      ? preview.currentTime * 1000000
      : main
        ? Number(main.clip.start_us || 0) +
          (preview.currentTime * 1000000 - Number(main.clip.source_in_us || 0)) /
          Number(main.clip.playback_rate || 1)
        : preview.currentTime * 1000000;
    playheadUs = Math.max(0, mapped);
    if (seek) seek.value = String(Math.round(playheadUs));
    if (byId("playhead-time")) byId("playhead-time").textContent = formatTime(playheadUs);
    document.querySelectorAll(".timeline-playhead").forEach((line) => {
      line.style.left = (playheadUs / 1000000 * timelinePixelsPerSecond) + "px";
    });
  });
  const timelineTab = byId("studio-tab-timeline");
  if (timelineTab) timelineTab.addEventListener("click", () => setView("timeline"));
  const mediaTab = byId("studio-tab-media");
  if (mediaTab) mediaTab.addEventListener("click", () => setView("media"));
  const clearSelection = byId("studio-clear-selection");
  if (clearSelection) clearSelection.addEventListener("click", () => {
    selectedClipId = "";
    selectedClipIds.clear();
    updateInspector();
    renderMediaBin();
  });
  const refresh = byId("refresh-studio-project");
  if (refresh) refresh.addEventListener("click", () => {
    if (typeof window.loadProject === "function") window.loadProject(false);
  });

  const run = async (calls, confirmations = []) => {
    try {
      await submitOperations(calls, confirmations);
    } catch (error) {
      const status = byId("render-status");
      if (status) {
        status.textContent = error.message;
        status.className = "status error";
      }
    }
  };
  const selected = () => findSelectedClip();
  const numeric = (id) => {
    const value = Number(byId(id)?.value);
    if (!Number.isFinite(value)) throw new Error("Enter a valid number in " + id + ".");
    return value;
  };
  const click = (id, callback) => {
    const button = byId(id);
    if (button) button.addEventListener("click", () => {
      try { Promise.resolve(callback()).catch((error) => {
        const status = byId("render-status");
        if (status) { status.textContent = error.message; status.className = "status error"; }
      }); } catch (error) {
        const status = byId("render-status");
        if (status) { status.textContent = error.message; status.className = "status error"; }
      }
    });
  };

  click("studio-review-silence", async () => {
    const item = selected();
    if (!item || !["video", "audio"].includes(item.clip.kind)) {
      throw new Error("Select a video or audio source clip first.");
    }
    const transcriptId = byId("studio-silence-transcript")?.value;
    if (!transcriptId) throw new Error("Load or import a timed transcript first.");
    const seconds = numeric("studio-silence-analysis-seconds");
    const threshold = numeric("studio-silence-threshold");
    const minimumUs = Math.round(numeric("studio-silence-minimum-ms") * 1000);
    if (seconds < 1 || seconds > 600) throw new Error("Audio scan limit must be 1–600 seconds.");
    if (threshold < -80 || threshold > -10) throw new Error("Silence threshold must be -80 to -10 dB.");
    if (minimumUs < 20000 || minimumUs > 10000000) throw new Error("Minimum silence must be 20–10,000 milliseconds.");
    const status = byId("studio-silence-status");
    const host = byId("studio-silence-candidates");
    if (host) host.replaceChildren();
    if (status) status.textContent = "Silence measurement queued. This runs in the cloud without rendering a new video.";
    await submitOperations([{
      name: "transcript.review_silence",
      arguments: {
        transcript_id: transcriptId,
        clip_id: item.clip.id,
        analysis_seconds: seconds,
        silence_threshold_db: threshold,
        minimum_silence_us: minimumUs
      }
    }]);
  });

  click("studio-save-text", () => {
    const item = selected();
    if (!item || item.clip.kind !== "text") throw new Error("Select a text or caption clip first.");
    const content = byId("studio-text-content").value;
    if (!content.trim()) throw new Error("Text or caption content cannot be empty.");
    const textStyle = {
      family: byId("studio-text-family").value.trim() || "Sans",
      size: Math.round(numeric("studio-text-size")),
      fgcolour: byId("studio-text-fgcolour").value.trim(),
      olcolour: byId("studio-text-olcolour").value.trim(),
      outline: Math.round(numeric("studio-text-outline")),
      weight: Math.round(numeric("studio-text-weight")),
      background_fill: Boolean(byId("studio-text-background-fill").checked),
      bgcolour: byId("studio-text-bgcolour").value,
      bgopacity: numeric("studio-text-bgopacity"),
      pad: Math.round(numeric("studio-text-pad")),
      shadow_color: byId("studio-text-shadow-color").value,
      shadow_x: Math.round(numeric("studio-text-shadow-x")),
      shadow_y: Math.round(numeric("studio-text-shadow-y")),
      shadow_opacity: numeric("studio-text-shadow-opacity"),
      shadow_blur: numeric("studio-text-shadow-blur"),
      letter_spacing_px: numeric("studio-text-letter-spacing"),
      line_spacing_px: Math.round(numeric("studio-text-line-spacing")),
      halign: byId("studio-text-halign").value,
      valign: byId("studio-text-valign").value,
      x_percent: numeric("studio-text-x"),
      y_percent: numeric("studio-text-y"),
      width_percent: numeric("studio-text-width"),
      height_percent: numeric("studio-text-height")
    };
    const colourPattern = /^(#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?|0x[0-9a-fA-F]{8}|white|black|red|green|blue)$/i;
    if (!colourPattern.test(textStyle.fgcolour) || !colourPattern.test(textStyle.olcolour) ||
        !colourPattern.test(textStyle.bgcolour) || !colourPattern.test(textStyle.shadow_color)) {
      throw new Error("Use a supported colour name or a hex colour such as #FFFFFF.");
    }
    if (textStyle.x_percent + textStyle.width_percent > 100 ||
        textStyle.y_percent + textStyle.height_percent > 100) {
      throw new Error("The text box must stay inside the video frame.");
    }
    return run([{
      name: "text.update_clip",
      arguments: {clip_id: item.clip.id, content, text_style: textStyle}
    }]);
  });

  click("studio-export-subtitles", () => {
    const trackId = byId("studio-subtitle-track")?.value;
    const track = (currentProject?.tracks || []).find((item) => item.id === trackId);
    if (!track) throw new Error("Choose an unlocked text track first.");
    const captionIO = window.VideoEditorCaptionIO;
    if (!captionIO) throw new Error("Subtitle export tools are not ready. Refresh the Studio and try again.");
    const format = byId("studio-subtitle-format")?.value || "srt";
    const content = captionIO.exportSubtitleTrack(track, format);
    const blob = new Blob([content], {
      type: format === "vtt" ? "text/vtt;charset=utf-8" : "application/x-subrip;charset=utf-8"
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    const safeName = String(currentProject?.name || "captions")
      .toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64) || "captions";
    anchor.href = url;
    anchor.download = safeName + "." + format;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    const status = byId("studio-subtitle-status");
    if (status) {
      status.textContent = "Exported " + format.toUpperCase() + " from " + track.name + ".";
      status.className = "status success";
    }
  });

  click("studio-group-clips", () => {
    const clipIds = [...selectedClipIds];
    if (clipIds.length < 2) throw new Error("Hold Shift and select at least two clips first.");
    return run([{name:"timeline.group_clips",arguments:{clip_ids:clipIds,name:"Linked clips"}}]);
  });
  click("studio-ungroup-clips", () => {
    const clipIds = [...selectedClipIds];
    if (!clipIds.length) throw new Error("Select grouped clips first.");
    return run([{name:"timeline.ungroup_clips",arguments:{clip_ids:clipIds}}]);
  });
  click("studio-add-marker", () => {
    const label = byId("timeline-marker-label").value.trim();
    if (!label) throw new Error("Enter a marker label.");
    return run([{name:"timeline.add_marker",arguments:{time_us:Math.max(0,Math.round(playheadUs)),label}}]);
  });
  click("studio-move-clip", () => {
    const item = selected(); if (!item) throw new Error("Select a clip first.");
    return run([{name:"timeline.move_clip",arguments:{clip_id:item.clip.id,start_us:secondsToUs(numeric("clip-start-seconds"))}}]);
  });
  click("studio-trim-clip", () => {
    const item = selected(); if (!item) throw new Error("Select a clip first.");
    const sourceIn = secondsToUs(numeric("clip-source-in"));
    const sourceOut = secondsToUs(numeric("clip-source-out"));
    if (sourceOut <= sourceIn) throw new Error("Source out must be later than source in.");
    return run([{name:"timeline.trim_clip",arguments:{clip_id:item.clip.id,source_in_us:sourceIn,source_out_us:sourceOut}}]);
  });
  click("studio-slip-clip", () => {
    const item = selected(); if (!item) throw new Error("Select a clip first.");
    if (!["video", "audio"].includes(item.clip.kind)) {
      throw new Error("Slip editing is currently available for video/audio clips only.");
    }
    const offsetSeconds = numeric("clip-slip-offset");
    const deltaUs = Math.round(offsetSeconds * 1000000);
    if (!Number.isSafeInteger(deltaUs) || deltaUs === 0) {
      throw new Error("Enter a non-zero slip offset in seconds.");
    }
    return run([{name:"timeline.slip_clip",arguments:{
      clip_id:item.clip.id,delta_us:deltaUs
    }}]);
  });
  click("studio-apply-speed", () => {
    const item = selected(); if (!item) throw new Error("Select a clip first.");
    return run([{name:"clip.set_speed",arguments:{
      clip_id:item.clip.id,playback_rate:numeric("clip-speed")
    }}]);
  });
  click("studio-split-clip", () => {
    const item = selected(); if (!item) throw new Error("Select a clip first.");
    const local = playheadUs - Number(item.clip.start_us || 0);
    if (local <= 0 || local >= Number(item.clip.duration_us || 0)) throw new Error("Move the playhead inside the selected clip before splitting.");
    return run([{name:"timeline.split_clip",arguments:{clip_id:item.clip.id,at_us:Math.round(local)}}]);
  });
  click("studio-duplicate-clip", () => {
    const item = selected(); if (!item) throw new Error("Select a clip first.");
    return run([{name:"timeline.duplicate_clip",arguments:{
      clip_id:item.clip.id,start_us:Number(item.clip.start_us || 0)+Number(item.clip.duration_us || 0)
    }}]);
  });
  click("studio-delete-clip", () => {
    const item = selected(); if (!item) throw new Error("Select a clip first.");
    if (!window.confirm("Delete this clip? This cannot be undone after it is rendered.")) return;
    return run([{name:"timeline.delete_clip",arguments:{clip_id:item.clip.id}}],["timeline.delete_clip"]);
  });
  click("studio-apply-framing", () => {
    const item = selected(); if (!item) throw new Error("Select a clip first.");
    const mode = byId("clip-framing").value;
    const calls = [];
    if (mode !== "none" && item.clip.crop) {
      calls.push({name:"clip.set_crop",arguments:{
        clip_id:item.clip.id,mode:"none"
      }});
    }
    calls.push({name:"clip.set_framing",arguments:{
      clip_id:item.clip.id,mode,
      horizontal_alignment:byId("clip-horizontal").value,
      vertical_alignment:byId("clip-vertical").value
    }});
    return run(calls);
  });
  click("studio-apply-crop", () => {
    const item = selected(); if (!item) throw new Error("Select a clip first.");
    if (!["video", "image"].includes(item.clip.kind)) {
      throw new Error("Manual crop is available for video and image clips only.");
    }
    const x = numeric("clip-crop-x") / 100;
    const y = numeric("clip-crop-y") / 100;
    const width = numeric("clip-crop-width") / 100;
    const height = numeric("clip-crop-height") / 100;
    if (x < 0 || y < 0 || width <= 0 || height <= 0 ||
        x + width > 1.000000001 || y + height > 1.000000001) {
      throw new Error("Crop must remain inside the source frame. Adjust left/top or reduce width/height.");
    }
    const calls = [];
    if (item.clip.framing) {
      calls.push({name:"clip.set_framing",arguments:{
        clip_id:item.clip.id,mode:"none"
      }});
    }
    calls.push({name:"clip.set_crop",arguments:{
      clip_id:item.clip.id,mode:"custom",x,y,width,height
    }});
    return run(calls);
  });
  click("studio-reset-crop", () => {
    const item = selected(); if (!item) throw new Error("Select a clip first.");
    return run([{name:"clip.set_crop",arguments:{
      clip_id:item.clip.id,mode:"none"
    }}]);
  });
  click("studio-apply-transform", () => {
    const item = selected(); if (!item) throw new Error("Select a clip first.");
    return run([{name:"clip.set_transform",arguments:{
      clip_id:item.clip.id,
      position_x:numeric("clip-position-x"),position_y:numeric("clip-position-y"),
      scale_x:numeric("clip-scale-x"),scale_y:numeric("clip-scale-y"),
      rotation_deg:numeric("clip-rotation"),opacity:numeric("clip-opacity"),
      anchor_x:numeric("clip-anchor-x")/100,anchor_y:numeric("clip-anchor-y")/100,
      flip_horizontal:Boolean(byId("clip-flip-horizontal").checked),
      flip_vertical:Boolean(byId("clip-flip-vertical").checked)
    }}]);
  });
  click("studio-add-keyframe", () => {
    const item = selected(); if (!item) throw new Error("Select a clip first.");
    const property = byId("keyframe-property").value;
    return run([{name:"animation.set_keyframe",arguments:{
      clip_id:item.clip.id,property,time_us:secondsToUs(numeric("keyframe-time")),
      value:numeric("keyframe-value"),interpolation:byId("keyframe-interpolation").value
    }}]);
  });
  click("studio-remove-keyframe", () => {
    const item = selected(); if (!item) throw new Error("Select a clip first.");
    return run([{name:"animation.remove_keyframe",arguments:{
      clip_id:item.clip.id,property:byId("keyframe-property").value,
      time_us:secondsToUs(numeric("keyframe-time"))
    }}]);
  });
  click("studio-reset-keyframes", () => {
    const item=selected();if(!item)throw new Error("Select a clip first.");
    return run([{name:"animation.clear_keyframes",arguments:{
      clip_id:item.clip.id,property:byId("keyframe-property").value
    }}]);
  });
  click("studio-reset-all-keyframes", () => {
    const item=selected();if(!item)throw new Error("Select a clip first.");
    if(!window.confirm("Clear every keyframe on this clip?"))return;
    return run([{name:"animation.clear_keyframes",arguments:{clip_id:item.clip.id}}]);
  });
  click("studio-copy-keyframes", () => {
    const item = selected(); if (!item) throw new Error("Select a clip first.");
    const frames = Array.isArray(item.clip.keyframes) ? item.clip.keyframes : [];
    if (!frames.length) throw new Error("The selected clip has no keyframes to copy.");
    if (frames.length > 20) throw new Error("Copying more than 20 keyframes at once is not supported.");
    keyframeClipboard = JSON.parse(JSON.stringify(frames));
    const status=byId("render-status");
    if(status){status.textContent=frames.length+" keyframe(s) copied. Select another clip and paste.";status.className="status success";}
  });
  click("studio-paste-keyframes", () => {
    const item = selected(); if (!item) throw new Error("Select a clip first.");
    if (!keyframeClipboard.length) throw new Error("Copy keyframes first.");
    if (keyframeClipboard.some((frame) => Number(frame.time_us) > Number(item.clip.duration_us || 0))) {
      throw new Error("The copied keyframes do not fit inside the selected clip.");
    }
    const calls=keyframeClipboard.map((frame)=>({
      name:"animation.set_keyframe",
      arguments:{
        clip_id:item.clip.id,property:frame.property,time_us:frame.time_us,
        value:frame.value,interpolation:frame.interpolation || "linear",
        ...(frame.bezier ? {bezier:frame.bezier} : {})
      }
    }));
    return run(calls);
  });
  click("studio-apply-motion-preset", () => {
    const item=selected(); if(!item)throw new Error("Select a clip first.");
    const clip=item.clip;
    const duration=Math.max(1,Number(clip.duration_us||1));
    const preset=byId("motion-preset").value;
    const windowUs=Math.min(600000,duration);
    const calls=[];
    const add=(property,time_us,value,interpolation="ease_in_out")=>{
      calls.push({name:"animation.set_keyframe",arguments:{
        clip_id:clip.id,property,time_us,value,interpolation
      }});
    };
    if(preset==="fade_in"||preset==="fade_out"){
      if(!["video","image","text"].includes(clip.kind))throw new Error("Fade presets require a visual or text clip.");
      if(preset==="fade_in"){
        add("opacity",0,0,clip.kind==="text"?"linear":"ease_out");
        add("opacity",windowUs,1,clip.kind==="text"?"linear":"ease_out");
      }else{
        add("opacity",duration-windowUs,1,clip.kind==="text"?"linear":"ease_in");
        add("opacity",duration,0,clip.kind==="text"?"linear":"ease_in");
      }
    }else if(preset==="zoom_in"){
      if(!["video","image"].includes(clip.kind))throw new Error("Zoom presets require a video or image clip.");
      add("scale_x",0,0.9,"ease_out");add("scale_x",windowUs,1,"ease_out");
      add("scale_y",0,0.9,"ease_out");add("scale_y",windowUs,1,"ease_out");
    }else if(preset==="zoom_out"){
      if(!["video","image"].includes(clip.kind))throw new Error("Zoom presets require a video or image clip.");
      add("scale_x",0,1.15,"ease_out_quart");add("scale_x",windowUs,1,"ease_out_quart");
      add("scale_y",0,1.15,"ease_out_quart");add("scale_y",windowUs,1,"ease_out_quart");
    }else if(preset==="pan_left"||preset==="pan_right"){
      if(!["video","image"].includes(clip.kind))throw new Error("Pan presets require a video or image clip.");
      const from=preset==="pan_left"?80:-80;
      add("position_x",0,from,"ease_in_out");add("position_x",windowUs,0,"ease_in_out");
    }else if(preset==="crop_reveal"){
      if(!["video","image"].includes(clip.kind))throw new Error("Animated crop requires a video or image clip.");
      if(clip.framing)throw new Error("Clear automatic framing before using an animated crop preset.");
      add("crop_x",0,0.08,"ease_in_out");add("crop_x",windowUs,0,"ease_in_out");
      add("crop_y",0,0.08,"ease_in_out");add("crop_y",windowUs,0,"ease_in_out");
      add("crop_width",0,0.84,"ease_in_out");add("crop_width",windowUs,1,"ease_in_out");
      add("crop_height",0,0.84,"ease_in_out");add("crop_height",windowUs,1,"ease_in_out");
    }else if(preset==="speed_ramp"){
      if(clip.kind!=="video")throw new Error("Speed ramp presets require a video clip.");
      add("playback_rate",0,0.75,"ease_in_out");
      add("playback_rate",Math.round(duration/2),1.5,"ease_in_out");
      add("playback_rate",duration,1,"ease_in_out");
    }else throw new Error("Unknown motion preset.");
    return run(calls);
  });
  click("studio-add-track", () => {
    const type = byId("new-track-type").value;
    const name = byId("new-track-name").value.trim();
    if (!name) throw new Error("Enter a track name.");
    const order=Math.max(-1,...(currentProject?.tracks || []).map((track)=>Number(track.order)||0))+1;
    return run([{name:"timeline.add_track",arguments:{
      track_type:type,name,order
    }}]);
  });
  click("studio-rename-track", () => {
    const track = selectedTrack(); if (!track) throw new Error("Select a track.");
    const name = byId("rename-track").value.trim();
    if (!name) throw new Error("Enter the new track name.");
    return run([{name:"track.rename",arguments:{track_id:track.id,name}}]);
  });
  click("studio-reorder-track", () => {
    const track = selectedTrack(); if (!track) throw new Error("Select a track.");
    const order = Math.round(numeric("track-order"));
    if (!Number.isInteger(order) || order < 0) throw new Error("Track position must be zero or higher.");
    return run([{name:"track.reorder",arguments:{track_id:track.id,order}}]);
  });
  click("studio-lock-track", () => {
    const track = selectedTrack(); if (!track) throw new Error("Select a track.");
    return run([{name:"track.set_locked",arguments:{track_id:track.id,locked:!Boolean(track.locked)}}]);
  });
  click("studio-toggle-track-enabled", () => {
    const track=selectedTrack();if(!track)throw new Error("Select a track.");
    return run([{name:"track.set_state",arguments:{track_id:track.id,enabled:track.enabled===false}}]);
  });
  click("studio-toggle-track-muted", () => {
    const track=selectedTrack();if(!track)throw new Error("Select a track.");
    return run([{name:"track.set_state",arguments:{track_id:track.id,muted:!Boolean(track.muted)}}]);
  });
  click("studio-toggle-track-visible", () => {
    const track=selectedTrack();if(!track)throw new Error("Select a track.");
    if(track.type==="audio")throw new Error("Audio tracks do not have a visual layer.");
    return run([{name:"track.set_state",arguments:{track_id:track.id,visible:track.visible===false}}]);
  });
  click("studio-toggle-track-solo", () => {
    const track=selectedTrack();if(!track)throw new Error("Select a track.");
    return run([{name:"track.set_state",arguments:{track_id:track.id,solo:!Boolean(track.solo)}}]);
  });
  click("studio-apply-track-audio", () => {
    const track=selectedTrack();if(!track)throw new Error("Select a track.");
    if(track.type==="text")throw new Error("Text tracks do not carry an audio signal.");
    return run([{name:"track.set_state",arguments:{
      track_id:track.id,
      audio_gain_db:numeric("track-audio-gain"),
      audio_pan:numeric("track-audio-pan")
    }}]);
  });
  click("studio-remove-track", () => {
    const track = selectedTrack(); if (!track) throw new Error("Select a track.");
    if (!window.confirm("Remove this track and all clips on it?")) return;
    return run([{name:"timeline.remove_track",arguments:{track_id:track.id}}],["timeline.remove_track"]);
  });
  click("studio-set-profile", () => {
    return run([{name:"project.set_profile",arguments:{
      width:Math.round(numeric("profile-width")),height:Math.round(numeric("profile-height")),
      fps_numerator:Math.round(numeric("profile-fps-num")),fps_denominator:Math.round(numeric("profile-fps-den"))
    }}]);
  });
  const preset=byId("profile-preset");
  if(preset)preset.addEventListener("change",()=>{
    const sizes={"9:16":[1080,1920],"16:9":[1920,1080],"1:1":[1080,1080],"4:5":[1080,1350]};
    const size=sizes[preset.value];
    if(size){byId("profile-width").value=String(size[0]);byId("profile-height").value=String(size[1]);}
  });
  click("studio-undo", () => run([{name:"history.undo",arguments:{}}]));
  click("studio-redo", () => run([{name:"history.redo",arguments:{}}]));
  const trackSelector = byId("manage-track");
  if (trackSelector) trackSelector.addEventListener("change", () => {
    const track = selectedTrack();
    if (track && byId("rename-track")) byId("rename-track").value = track.name;
    if (track && byId("track-order")) byId("track-order").value = String(track.order);
    if (byId("track-audio-gain")) byId("track-audio-gain").value = String(track?.audio_gain_db ?? 0);
    if (byId("track-audio-pan")) byId("track-audio-pan").value = String(track?.audio_pan ?? 0);
    if (byId("studio-apply-track-audio")) byId("studio-apply-track-audio").disabled = !track || track.type === "text";
    if (byId("studio-lock-track")) byId("studio-lock-track").textContent = track?.locked ? "Unlock track" : "Lock track";
    if (byId("studio-toggle-track-enabled")) byId("studio-toggle-track-enabled").textContent = track?.enabled === false ? "Enable track" : "Disable track";
    if (byId("studio-toggle-track-visible")) {
      byId("studio-toggle-track-visible").textContent = track?.visible === false ? "Show visuals" : "Hide visuals";
      byId("studio-toggle-track-visible").disabled = !track || track.type === "audio";
      byId("studio-toggle-track-visible").title = track?.type === "audio"
        ? "Audio tracks do not have a visual layer."
        : "Hide the video/text layer but keep its audio unless muted.";
    }
    if (byId("studio-toggle-track-muted")) byId("studio-toggle-track-muted").textContent = track?.muted ? "Unmute track" : "Mute track";
    if (byId("studio-toggle-track-solo")) {
      byId("studio-toggle-track-solo").textContent = track?.solo ? "Unsolo track" : "Solo track";
      byId("studio-toggle-track-solo").disabled = !track || track.type === "text";
      byId("studio-toggle-track-solo").title = track?.type === "text"
        ? "Solo is available for video, overlay and audio tracks."
        : "Solo this track in the render.";
    }
    renderMediaBin();
  });
})();
