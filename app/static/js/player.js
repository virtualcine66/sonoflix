/* Sem sintaxe moderna: este arquivo também precisa executar em navegadores de TV. */
(function () {
  "use strict";
  var root = document.querySelector("[data-player]");
  if (!root) return;
  function find(name) { return root.querySelector("[data-" + name + "]"); }
  var video = find("video"), screen = find("screen"), play = find("play");
  var seek = find("seek"), status = find("status"), resume = find("resume");
  var quality = find("quality"), hls = null, saved = 0, lastSave = 0, pending = 0;
  var nativeControls = false, hasStarted = false, failed = false;
  var key = root.getAttribute("data-progress-key");
  var source = root.getAttribute("data-source");
  var format = root.getAttribute("data-type");
  if (format === "auto") format = /\.m3u8(?:[?#]|$)/i.test(source) ? "hls" : "file";

  function time(value) {
    if (!isFinite(value) || value < 0) return "--:--";
    value = Math.floor(value);
    var hours = Math.floor(value / 3600), minutes = Math.floor(value % 3600 / 60), seconds = value % 60;
    return (hours ? hours + ":" : "") + (minutes < 10 ? "0" : "") + minutes + ":" + (seconds < 10 ? "0" : "") + seconds;
  }
  function message(text, error) {
    if (failed && !error) return;
    if (error) failed = true;
    status.textContent = text;
    status.classList.toggle("is-error", !!error);
    find("retry").hidden = !error;
  }
  function store(clear) {
    if (!hasStarted && !clear) return;
    try {
      if (clear || video.ended || (isFinite(video.duration) && video.duration - video.currentTime < 10)) {
        localStorage.removeItem(key);
      } else if (video.currentTime >= 5) {
        localStorage.setItem(key, String(Math.floor(video.currentTime)));
      }
    } catch (ignore) { /* Modo privado e TVs podem bloquear o armazenamento. */ }
  }
  try { saved = Number(localStorage.getItem(key)) || 0; } catch (ignore) {}
  function start() {
    resume.hidden = true;
    hasStarted = true;
    var result;
    try {
      result = video.play();
      if (result && result.catch) result.catch(function (error) {
        if (error.name === "NotAllowedError") message("Pressione Reproduzir para iniciar neste aparelho.");
        else if (error.name !== "AbortError") message("Não foi possível iniciar. Verifique o link e o formato do vídeo.", true);
      });
    } catch (error) { message("Este aparelho não conseguiu iniciar o vídeo.", true); }
  }
  function toggle() {
    if (!resume.hidden) { resume.hidden = true; saved = 0; }
    if (video.paused || video.ended) start(); else video.pause();
  }
  function jump(delta) {
    if (video.seekable.length) {
      var first = video.seekable.start(0), last = video.seekable.end(video.seekable.length - 1);
      video.currentTime = Math.min(last, Math.max(first, video.currentTime + delta));
    } else if (isFinite(video.duration)) {
      video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + delta));
    }
  }
  function update() {
    var finite = isFinite(video.duration) && video.duration > 0;
    find("current").textContent = time(video.currentTime);
    find("duration").textContent = finite ? time(video.duration) : "Ao vivo";
    seek.disabled = !finite;
    if (finite) {
      seek.max = String(Math.floor(video.duration));
      seek.value = String(Math.floor(video.currentTime));
      seek.setAttribute("aria-valuetext", time(video.currentTime) + " de " + time(video.duration));
    }
  }
  function loaded() {
    update();
    if (pending && isFinite(video.duration)) {
      video.currentTime = Math.min(pending, Math.max(0, video.duration - 1));
      pending = 0;
    }
    if (saved >= 5 && isFinite(video.duration) && saved < video.duration - 10 && !hasStarted) {
      find("resume-text").textContent = "Você parou em " + time(saved) + ". Deseja continuar?";
      resume.hidden = false;
    }
  }
  function load() {
    failed = false;
    if (hls) { hls.destroy(); hls = null; }
    quality.innerHTML = '<option value="-1">Automática</option>';
    find("quality-label").hidden = true;
    message("Carregando vídeo…");
    if (format === "hls" && !video.canPlayType("application/vnd.apple.mpegurl")) {
      if (!window.Hls) {
        var library = root.getAttribute("data-hls-library");
        if (!library) { message("A biblioteca de reprodução não está disponível.", true); return; }
        var script = document.createElement("script");
        script.src = library;
        play.disabled = true;
        script.onload = function () { play.disabled = false; load(); };
        script.onerror = function () {
          play.disabled = false;
          script.parentNode.removeChild(script);
          message("Não foi possível carregar o suporte a HLS. Tente novamente.", true);
        };
        document.head.appendChild(script);
        return;
      }
      if (!window.Hls.isSupported()) {
        video.removeAttribute("src");
        video.load();
        message("Este navegador não oferece suporte a HLS. Use uma fonte MP4 ou um aparelho com suporte a HLS.", true);
        return;
      }
      video.removeAttribute("src");
      video.load();
      hls = new window.Hls({ enableWorker: true, maxBufferLength: 30, backBufferLength: 30 });
      hls.on(window.Hls.Events.MANIFEST_PARSED, function () {
        if (!hasStarted) message("Pronto. Pressione Reproduzir.");
        hls.levels.forEach(function (level, index) {
          var option = document.createElement("option");
          option.value = String(index);
          option.textContent = level.height ? level.height + "p" : Math.round(level.bitrate / 1000) + " kb/s";
          quality.appendChild(option);
        });
        find("quality-label").hidden = hls.levels.length < 2;
      });
      hls.on(window.Hls.Events.ERROR, function (event, data) {
        if (data.fatal) {
          message("Falha no stream. Confira a conexão, a validade do link e a permissão CORS no servidor de vídeo.", true);
          hls.destroy(); hls = null;
        }
      });
      hls.loadSource(source);
      hls.attachMedia(video);
    } else {
      video.src = source;
      video.load();
    }
  }
  function fullscreen() {
    try {
      var result;
      if (document.fullscreenElement || document.webkitFullscreenElement) {
        result = document.exitFullscreen ? document.exitFullscreen() : document.webkitExitFullscreen();
      } else if (screen.classList.contains("is-expanded")) {
        screen.classList.remove("is-expanded");
      } else if (screen.requestFullscreen || screen.webkitRequestFullscreen) {
        result = screen.requestFullscreen ? screen.requestFullscreen() : screen.webkitRequestFullscreen();
      } else if (video.webkitEnterFullscreen) {
        video.webkitEnterFullscreen();
      } else { screen.classList.add("is-expanded"); }
      if (result && result.catch) result.catch(function () { screen.classList.add("is-expanded"); });
    } catch (error) { screen.classList.toggle("is-expanded"); }
  }
  function back() {
    if (!find("options").hidden) {
      find("options").hidden = true;
      find("options-toggle").setAttribute("aria-expanded", "false");
      find("options-toggle").focus();
      return;
    }
    if (document.fullscreenElement || document.webkitFullscreenElement || screen.classList.contains("is-expanded")) {
      fullscreen();
    } else { window.location.href = find("back").href; }
  }
  find("options-toggle").addEventListener("click", function () {
    var open = find("options").hidden;
    find("options").hidden = !open;
    this.setAttribute("aria-expanded", String(open));
    if (open) find("volume").focus();
  });
  play.addEventListener("click", toggle);
  find("rewind").addEventListener("click", function () { jump(-10); });
  find("forward").addEventListener("click", function () { jump(10); });
  find("continue").addEventListener("click", function () {
    video.currentTime = saved; saved = 0; start(); play.focus();
  });
  find("restart").addEventListener("click", function () {
    saved = 0; video.currentTime = 0; store(true); start(); play.focus();
  });
  seek.addEventListener("input", function () { video.currentTime = Number(seek.value); update(); });
  find("mute").addEventListener("click", function () { video.muted = !video.muted; });
  find("volume").addEventListener("input", function () { video.volume = Number(this.value); video.muted = video.volume === 0; });
  find("speed").addEventListener("change", function () { video.playbackRate = Number(this.value); });
  quality.addEventListener("change", function () { if (hls) hls.currentLevel = Number(this.value); });
  find("captions").addEventListener("click", function () {
    var enabled = this.getAttribute("aria-pressed") !== "true";
    for (var i = 0; i < video.textTracks.length; i++) video.textTracks[i].mode = enabled ? "showing" : "disabled";
    this.setAttribute("aria-pressed", String(enabled));
  });
  find("captions").hidden = !video.querySelector("track");
  find("fullscreen").addEventListener("click", fullscreen);
  find("retry").addEventListener("click", function () { pending = video.currentTime; hasStarted = false; load(); });
  find("native").addEventListener("click", function () {
    nativeControls = !nativeControls;
    video.controls = nativeControls;
    this.textContent = nativeControls ? "Usar controles do site" : "Usar controles do aparelho";
    video.focus();
  });
  find("tv").addEventListener("click", function () {
    var enabled = root.classList.toggle("tv-mode");
    this.setAttribute("aria-pressed", String(enabled));
  });
  if (document.pictureInPictureEnabled && video.requestPictureInPicture) {
    find("pip").hidden = false;
    find("pip").addEventListener("click", function () {
      var result;
      try {
        result = document.pictureInPictureElement ? document.exitPictureInPicture() : video.requestPictureInPicture();
        if (result && result.catch) result.catch(function () { message("Miniplayer indisponível neste momento."); });
      } catch (error) { message("Miniplayer indisponível neste aparelho."); }
    });
  }
  video.addEventListener("loadedmetadata", loaded);
  video.addEventListener("durationchange", update);
  video.addEventListener("timeupdate", function () {
    update();
    if (Date.now() - lastSave > 5000) { store(false); lastSave = Date.now(); }
  });
  video.addEventListener("play", function () {
    hasStarted = true; resume.hidden = true;
    play.textContent = "Ⅱ Pausar"; play.setAttribute("aria-label", "Pausar");
  });
  video.addEventListener("playing", function () { message("Reproduzindo"); });
  video.addEventListener("pause", function () {
    play.textContent = "▶ Reproduzir"; play.setAttribute("aria-label", "Reproduzir");
    if (!video.error) message(video.ended ? "Reprodução concluída." : "Pausado");
    store(false);
  });
  video.addEventListener("waiting", function () { message("Carregando… aguardando a conexão."); });
  video.addEventListener("canplay", function () { if (!hasStarted) message("Pronto. Pressione Reproduzir."); });
  video.addEventListener("volumechange", function () {
    var muted = video.muted || video.volume === 0;
    find("mute").textContent = muted ? "Som desligado" : "Som ligado";
    find("mute").setAttribute("aria-label", muted ? "Ativar som" : "Silenciar");
    find("mute").setAttribute("aria-pressed", String(muted));
    find("volume").value = String(video.volume);
  });
  video.addEventListener("error", function () {
    var code = video.error ? video.error.code : 0;
    message(code === 3 || code === 4 ? "Formato incompatível ou link inválido. Experimente MP4 com H.264 e áudio AAC." : "Não foi possível carregar. Verifique a conexão e as permissões do servidor de vídeo.", true);
  });
  video.addEventListener("ended", function () {
    store(true); message("Reprodução concluída.");
    if (find("next")) find("next").focus();
  });
  window.addEventListener("pagehide", function () { store(false); });
  document.addEventListener("visibilitychange", function () { if (document.hidden) store(false); });

  /* Navegação espacial: somente elementos visíveis, nunca interfere em selects/ranges. */
  function navigate(direction) {
    var active = document.activeElement;
    var nodes = root.querySelectorAll("a[href],button,input,select,video");
    var origin = active && active.getBoundingClientRect ? active.getBoundingClientRect() : video.getBoundingClientRect();
    var ox = origin.left + origin.width / 2, oy = origin.top + origin.height / 2;
    var best = null, score = Infinity;
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      if (node === active || node.disabled || !node.getClientRects().length) continue;
      if ((document.fullscreenElement || screen.classList.contains("is-expanded")) && !screen.contains(node)) continue;
      var rect = node.getBoundingClientRect();
      var dx = rect.left + rect.width / 2 - ox, dy = rect.top + rect.height / 2 - oy;
      var primary = direction === "ArrowRight" ? dx : direction === "ArrowLeft" ? -dx : direction === "ArrowDown" ? dy : -dy;
      var cross = direction === "ArrowLeft" || direction === "ArrowRight" ? Math.abs(dy) : Math.abs(dx);
      var distance = primary + cross * 3;
      if (primary > 5 && distance < score) { best = node; score = distance; }
    }
    if (best) { best.focus(); best.scrollIntoView({ block: "nearest", inline: "nearest" }); }
  }
  document.addEventListener("keydown", function (event) {
    var codes = { 13: "Enter", 27: "Escape", 37: "ArrowLeft", 38: "ArrowUp", 39: "ArrowRight", 40: "ArrowDown", 10009: "GoBack", 461: "GoBack", 415: "MediaPlay", 19: "MediaPause", 413: "MediaStop", 412: "MediaRewind", 417: "MediaFastForward", 10252: "MediaPlayPause" };
    var name = codes[event.keyCode] || event.key;
    var active = document.activeElement, tag = active ? active.tagName : "";
    if (name === "Escape" || name === "GoBack" || name === "BrowserBack") {
      event.preventDefault(); back(); return;
    }
    if (name === "MediaPlayPause") { event.preventDefault(); toggle(); return; }
    if (name === "MediaPlay") { event.preventDefault(); start(); return; }
    if (name === "MediaPause" || name === "MediaStop") { event.preventDefault(); video.pause(); return; }
    if (name === "MediaRewind" || name === "MediaFastForward") { event.preventDefault(); jump(name === "MediaRewind" ? -10 : 10); return; }
    if (tag === "TEXTAREA") return;
    if (tag === "INPUT" && name !== "ArrowUp" && name !== "ArrowDown") return;
    if (tag === "SELECT" && name !== "ArrowLeft" && name !== "ArrowRight") return;
    if (nativeControls && active === video) return;
    if ((name === "Enter" || name === " " || name === "Spacebar") && (active === video || active === document.body)) {
      event.preventDefault(); toggle();
    } else if (name === "ArrowLeft" || name === "ArrowRight" || name === "ArrowUp" || name === "ArrowDown") {
      event.preventDefault();
      if (active === video && (name === "ArrowLeft" || name === "ArrowRight")) jump(name === "ArrowLeft" ? -10 : 10);
      else navigate(name);
    }
  });
  function fullscreenChanged() {
    screen.classList.toggle("is-fullscreen", !!(document.fullscreenElement || document.webkitFullscreenElement));
  }
  document.addEventListener("fullscreenchange", fullscreenChanged);
  document.addEventListener("webkitfullscreenchange", fullscreenChanged);
  // Mantém o fallback HTML5 caso qualquer inicialização anterior falhe.
  find("controls").hidden = false;
  find("native").hidden = false;
  find("tv").hidden = false;
  video.controls = false;
  load();
  play.focus();
}());
