/**
 * OKAPI Chill — floating background-music widget (bottom-left).
 *
 * Two sources, one widget:
 *   • Radio   — free listener-supported stations, played by an <audio> element
 *               connected straight to the broadcaster.
 *   • YouTube — a user-built queue of pasted links, played by YouTube's own
 *               IFrame player.
 *
 * No audio passes through Flask either way; the server only serves the station
 * catalogue, parses pasted links and stores the queue (see src/music.py).
 *
 * Online-only by construction: the widget refuses to mount when the browser is
 * offline or the server's connectivity probe fails, so the user never presses
 * play and gets unexplained silence. It re-checks on the browser `online`
 * event, so plugging the network back in brings it up without a reload.
 *
 * YouTube's terms require the player to stay VISIBLE while it plays — the panel
 * therefore grows a video pane rather than hiding the iframe and keeping the
 * sound. Do not "fix" the layout by collapsing it away.
 */

(function () {
    'use strict';

    const SETTINGS_SAVE_DEBOUNCE_MS = 600;
    // A stream that has not produced audio by now is treated as unreachable.
    // Long enough for an icecast connect on lab Wi-Fi, short enough that the
    // spinner is not the whole experience.
    const CONNECT_TIMEOUT_MS = 12000;
    // How long an unplayable YouTube item stays on screen before the queue
    // moves on — long enough to read why, short enough not to strand playback.
    const SKIP_AFTER_ERROR_MS = 3500;
    const IFRAME_API_SRC = 'https://www.youtube.com/iframe_api';

    let stations = [];
    let queue = [];
    let currentId = null;
    let source = 'radio';
    let loopMode = 'all';
    let shuffle = false;
    let volume = 40;
    let queueIndex = -1;

    let audio = null;
    let player = null;          // YT.Player instance
    let playerReady = false;
    let pendingItem = null;     // item to start once the API finishes loading
    let apiLoading = false;

    let mounted = false;
    let panelOpen = false;
    let connectTimer = null;
    let skipTimer = null;
    let saveTimer = null;
    // True once the source has actually produced audio — distinguishes a
    // connect failure from a mid-stream hiccup.
    let connected = false;
    // Set when the panel closing paused a YouTube item, so reopening resumes it
    // but a deliberate pause is left alone.
    let pausedByPanel = false;

    function _t(key, fallback) {
        return (typeof t === 'function') ? t(key, fallback) : fallback;
    }

    function _escape(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function _station(id) {
        return stations.find(s => s.id === id) || stations[0] || null;
    }

    // ── Persistence ──────────────────────────────────────────────────────────
    // Preferences go through /settings; the queue has its own route because it
    // is content the user assembled, not a per-view preference.
    function _saveSettings(patch) {
        if (typeof USER_SETTINGS !== 'undefined') Object.assign(USER_SETTINGS, patch);
        clearTimeout(saveTimer);
        saveTimer = setTimeout(function () {
            fetch('/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(patch)
            }).catch(() => { /* preference only — a lost write is not worth a dialog */ });
        }, SETTINGS_SAVE_DEBOUNCE_MS);
    }

    function _saveQueue() {
        fetch('/music/queue', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ queue: queue })
        }).catch(() => { /* best effort */ });
    }

    // ── DOM ──────────────────────────────────────────────────────────────────

    function _buildDom() {
        const wrap = document.createElement('div');
        wrap.id = 'okapi-music';
        wrap.innerHTML = `
            <div id="okapi-music-panel" class="okapi-music-hidden" role="group"
                 aria-label="${_escape(_t('music.aria.panel', 'Background music'))}">
                <div id="okapi-music-head">
                    <span id="okapi-music-title">🎧 ${_escape(_t('music.title', 'Chill Radio'))}</span>
                    <button id="okapi-music-close" type="button"
                        data-hint="${_escape(_t('music.close', 'Close'))}"
                        aria-label="${_escape(_t('music.close', 'Close'))}">&#10005;</button>
                </div>

                <div id="okapi-music-tabs" role="tablist">
                    <button type="button" class="okapi-music-tab" data-source="radio" role="tab">
                        ${_escape(_t('music.source.radio', 'Radio'))}
                    </button>
                    <button type="button" class="okapi-music-tab" data-source="youtube" role="tab">YouTube</button>
                </div>

                <div id="okapi-music-radio">
                    <select id="okapi-music-station"
                        aria-label="${_escape(_t('music.aria.station', 'Station'))}"></select>
                    <p id="okapi-music-desc"></p>
                </div>

                <div id="okapi-music-youtube" class="okapi-music-hidden">
                    <!-- The player must stay visible while it plays (YouTube ToS). -->
                    <div id="okapi-music-video"><div id="okapi-music-video-mount"></div></div>
                    <div id="okapi-music-add-row">
                        <input id="okapi-music-add-input" type="text"
                            placeholder="${_escape(_t('music.paste_ph', 'Paste a YouTube link…'))}"
                            aria-label="${_escape(_t('music.paste_ph', 'Paste a YouTube link…'))}">
                        <button id="okapi-music-add-btn" type="button"
                            data-hint="${_escape(_t('music.add', 'Add to queue'))}"
                        aria-label="${_escape(_t('music.add', 'Add to queue'))}">＋</button>
                    </div>
                    <p id="okapi-music-track"></p>
                    <div id="okapi-music-queue-head">
                        <span id="okapi-music-queue-count"></span>
                        <button id="okapi-music-clear" type="button" class="okapi-music-link">
                            ${_escape(_t('music.clear', 'Clear'))}
                        </button>
                    </div>
                    <ul id="okapi-music-queue"></ul>
                </div>

                <div id="okapi-music-controls">
                    <button id="okapi-music-prev" type="button" class="okapi-music-btn okapi-music-btn--ghost okapi-music-hidden"
                        data-hint="${_escape(_t('music.previous', 'Previous'))}"
                        aria-label="${_escape(_t('music.previous', 'Previous'))}">⏮</button>
                    <button id="okapi-music-play" type="button" class="okapi-music-btn"
                        data-hint="${_escape(_t('music.play', 'Play'))}"
                        aria-label="${_escape(_t('music.play', 'Play'))}">
                        <span class="okapi-music-icon-play">▶</span>
                        <span class="okapi-music-icon-stop">■</span>
                    </button>
                    <button id="okapi-music-next" type="button" class="okapi-music-btn okapi-music-btn--ghost okapi-music-hidden"
                        data-hint="${_escape(_t('music.next', 'Next'))}"
                        aria-label="${_escape(_t('music.next', 'Next'))}">⏭</button>
                    <input id="okapi-music-vol" type="range" min="0" max="100" step="1"
                        aria-label="${_escape(_t('music.aria.volume', 'Volume'))}">
                    <span id="okapi-music-vol-value"></span>
                    <button id="okapi-music-loop" type="button" class="okapi-music-toggle okapi-music-hidden"
                        data-hint="${_escape(_t('music.loop', 'Repeat'))}"
                        aria-label="${_escape(_t('music.loop', 'Repeat'))}" aria-pressed="false">🔁</button>
                    <button id="okapi-music-shuffle" type="button" class="okapi-music-toggle okapi-music-hidden"
                        data-hint="${_escape(_t('music.shuffle', 'Shuffle'))}"
                        aria-label="${_escape(_t('music.shuffle', 'Shuffle'))}" aria-pressed="false">🔀</button>
                </div>

                <p id="okapi-music-status" aria-live="polite"></p>
            </div>
            <button id="okapi-music-fab" type="button"
                data-hint="${_escape(_t('music.fab_hint', 'Background music — free chill radio'))}"
                aria-label="${_escape(_t('music.fab_hint', 'Background music — free chill radio'))}">
                <span class="okapi-music-fab-icon">🎧</span>
                <span class="okapi-music-bars" aria-hidden="true"><i></i><i></i><i></i></span>
            </button>`;
        document.body.appendChild(wrap);

        const sel = document.getElementById('okapi-music-station');
        sel.innerHTML = stations.map(s =>
            `<option value="${_escape(s.id)}">${_escape(s.name)} — ${_escape(s.provider)}</option>`).join('');
        sel.value = currentId;
        document.getElementById('okapi-music-vol').value = volume;

        document.getElementById('okapi-music-fab').addEventListener('click', togglePanel);
        document.getElementById('okapi-music-close').addEventListener('click', closePanel);
        document.getElementById('okapi-music-play').addEventListener('click', toggle);
        document.getElementById('okapi-music-prev').addEventListener('click', function () { step(-1, true); });
        document.getElementById('okapi-music-next').addEventListener('click', function () { step(1, true); });
        document.getElementById('okapi-music-loop').addEventListener('click', cycleLoopMode);
        document.getElementById('okapi-music-shuffle').addEventListener('click', toggleShuffle);
        sel.addEventListener('change', function () { selectStation(this.value); });
        document.getElementById('okapi-music-vol').addEventListener('input', function () {
            setVolume(parseInt(this.value, 10));
        });
        document.getElementById('okapi-music-add-btn').addEventListener('click', addFromInput);
        document.getElementById('okapi-music-add-input').addEventListener('keydown', function (e) {
            if (e.key === 'Enter') { e.preventDefault(); addFromInput(); }
        });
        document.getElementById('okapi-music-clear').addEventListener('click', clearQueue);
        document.querySelectorAll('#okapi-music-tabs .okapi-music-tab').forEach(function (btn) {
            btn.addEventListener('click', function () { setSource(btn.dataset.source); });
        });
        // Delegated: the queue re-renders on every change.
        document.getElementById('okapi-music-queue').addEventListener('click', function (e) {
            const removeBtn = e.target.closest('.okapi-music-q-remove');
            if (removeBtn) { removeAt(parseInt(removeBtn.dataset.index, 10)); return; }
            const row = e.target.closest('.okapi-music-q-item');
            if (row) playIndex(parseInt(row.dataset.index, 10));
        });
        // Keyboard: each entry's title is its play control (role=button).
        document.getElementById('okapi-music-queue').addEventListener('keydown', function (e) {
            if (e.key !== 'Enter' && e.key !== ' ') return;
            const title = e.target.closest('.okapi-music-q-title');
            if (!title) return;
            e.preventDefault();
            const row = title.closest('.okapi-music-q-item');
            if (row) playIndex(parseInt(row.dataset.index, 10));
        });

        _renderSource();
        _renderStation();
        _renderVolume();
        _renderQueue();
        _renderModes();
    }

    function _renderSource() {
        const root = document.getElementById('okapi-music');
        if (!root) return;
        root.classList.toggle('is-youtube', source === 'youtube');
        root.querySelectorAll('.okapi-music-tab').forEach(function (btn) {
            const on = btn.dataset.source === source;
            btn.classList.toggle('is-active', on);
            btn.setAttribute('aria-selected', on ? 'true' : 'false');
        });
        document.getElementById('okapi-music-radio').classList.toggle('okapi-music-hidden', source !== 'radio');
        document.getElementById('okapi-music-youtube').classList.toggle('okapi-music-hidden', source !== 'youtube');
        ['okapi-music-prev', 'okapi-music-next', 'okapi-music-loop', 'okapi-music-shuffle'].forEach(function (id) {
            document.getElementById(id).classList.toggle('okapi-music-hidden', source !== 'youtube');
        });
    }

    function _renderStation() {
        const s = _station(currentId);
        const desc = document.getElementById('okapi-music-desc');
        if (desc) desc.textContent = s ? s.description : '';
    }

    function _renderVolume() {
        const out = document.getElementById('okapi-music-vol-value');
        if (out) out.textContent = volume + '%';
    }

    function _renderModes() {
        const loopBtn = document.getElementById('okapi-music-loop');
        if (loopBtn) {
            loopBtn.classList.toggle('is-active', loopMode !== 'off');
            loopBtn.textContent = loopMode === 'one' ? '🔂' : '🔁';
            loopBtn.dataset.hint = loopMode === 'off'
                ? _t('music.loop.off', 'Repeat: off')
                : (loopMode === 'one' ? _t('music.loop.one', 'Repeat: this item')
                                      : _t('music.loop.all', 'Repeat: whole queue'));
            loopBtn.setAttribute('aria-label', loopBtn.dataset.hint);
            loopBtn.setAttribute('aria-pressed', loopMode !== 'off' ? 'true' : 'false');
        }
        const shuffleBtn = document.getElementById('okapi-music-shuffle');
        if (shuffleBtn) {
            shuffleBtn.classList.toggle('is-active', shuffle);
            shuffleBtn.setAttribute('aria-pressed', shuffle ? 'true' : 'false');
        }
    }

    function _renderQueue() {
        const list = document.getElementById('okapi-music-queue');
        const count = document.getElementById('okapi-music-queue-count');
        if (!list) return;
        if (count) {
            count.textContent = _t('music.queue_count', 'Queue ({n})').replace('{n}', queue.length);
        }
        // The list is rebuilt on every change; keep a keyboard user's place.
        const focused = list.contains(document.activeElement) ? document.activeElement : null;
        const focusIndex = focused ? focused.closest('.okapi-music-q-item')?.dataset.index : null;
        const focusRemove = !!(focused && focused.classList.contains('okapi-music-q-remove'));
        // The title is the entry's play control: focusable, operable by key
        // (the list's keydown handler) and hinted with data-hint, not a
        // native title= (Rule.md §2.36).
        list.innerHTML = queue.map(function (item, i) {
            const badge = item.kind === 'playlist'
                ? `<span class="okapi-music-q-badge">${_escape(_t('music.playlist', 'playlist'))}</span>` : '';
            return `<li class="okapi-music-q-item${i === queueIndex ? ' is-current' : ''}" data-index="${i}"${i === queueIndex ? ' aria-current="true"' : ''}>
                        <span class="okapi-music-q-title" role="button" tabindex="0"
                            data-hint="${_escape(item.title)}">${_escape(item.title)}${badge}</span>
                        <button type="button" class="okapi-music-q-remove" data-index="${i}"
                            data-hint="${_escape(_t('music.remove', 'Remove'))}"
                            aria-label="${_escape(_t('music.remove', 'Remove'))}: ${_escape(item.title)}">&#10005;</button>
                    </li>`;
        }).join('');
        if (focusIndex != null) {
            const row = list.querySelector(`.okapi-music-q-item[data-index="${focusIndex}"]`);
            const target = row && row.querySelector(focusRemove ? '.okapi-music-q-remove' : '.okapi-music-q-title');
            if (target) target.focus();
        }
    }

    function _renderTrack(text) {
        const el = document.getElementById('okapi-music-track');
        if (el) el.textContent = text || '';
    }

    function _setStatus(text, kind) {
        const el = document.getElementById('okapi-music-status');
        if (!el) return;
        el.textContent = text || '';
        el.className = kind ? 'okapi-music-' + kind : '';
    }

    function _setPlaying(on) {
        const root = document.getElementById('okapi-music');
        if (root) root.classList.toggle('is-playing', !!on);
        const btn = document.getElementById('okapi-music-play');
        if (btn) {
            btn.dataset.hint = on ? _t('music.stop', 'Stop') : _t('music.play', 'Play');
            btn.setAttribute('aria-label', btn.dataset.hint);
        }
    }

    // ── Radio playback ───────────────────────────────────────────────────────

    function _clearConnectTimer() {
        clearTimeout(connectTimer);
        connectTimer = null;
    }

    function playRadio() {
        const s = _station(currentId);
        if (!s) return;
        stopAll(true);

        connected = false;
        const el = audio = new Audio();
        audio.preload = 'none';
        audio.volume = volume / 100;
        // Cache-bust: an icecast stream resumed from cache replays stale audio
        // and can start already-ended.
        audio.src = s.url + (s.url.indexOf('?') === -1 ? '?' : '&') + 'okapi=' + Date.now();
        audio.addEventListener('playing', function () {
            _clearConnectTimer();
            connected = true;
            _setStatus(_t('music.now_playing', 'Now playing: {s}').replace('{s}', s.name), 'ok');
            _setPlaying(true);
        });
        audio.addEventListener('error', _radioFailed);
        // `stalled` is only fatal *before* the first audio arrives. Mid-stream it
        // is a buffer underrun the browser routinely recovers from — treating it
        // as a failure there would kill a working station on a hiccup.
        // `audio === el` keeps a torn-down element from reporting a failure over
        // whatever the widget is doing now.
        audio.addEventListener('stalled', function () { if (!connected && audio === el) _radioFailed(); });

        _setStatus(_t('music.connecting', 'Connecting…'), '');
        _setPlaying(true);
        connectTimer = setTimeout(_radioFailed, CONNECT_TIMEOUT_MS);

        const p = audio.play();
        // Autoplay policies reject only when there was no user gesture; the
        // widget is click-driven, so a rejection here means the stream failed.
        if (p && typeof p.catch === 'function') p.catch(_radioFailed);
    }

    function _radioFailed() {
        stopAll(true);
        _setStatus(navigator.onLine
            ? _t('music.failed', 'Could not reach the station. Try another one.')
            : _t('music.offline', 'No internet connection — music is unavailable.'), 'error');
    }

    // ── YouTube playback ─────────────────────────────────────────────────────

    function _loadIframeApi(onReady) {
        if (window.YT && window.YT.Player) { onReady(); return; }
        // Chain onto any existing callback rather than overwriting it.
        const previous = window.onYouTubeIframeAPIReady;
        window.onYouTubeIframeAPIReady = function () {
            if (typeof previous === 'function') { try { previous(); } catch (e) { /* not ours */ } }
            onReady();
        };
        if (apiLoading) return;
        apiLoading = true;
        // Loaded lazily, only when the user actually opens the YouTube source —
        // a radio-only user never touches youtube.com.
        const tag = document.createElement('script');
        tag.src = IFRAME_API_SRC;
        tag.onerror = function () {
            apiLoading = false;
            _setStatus(_t('music.yt_api_failed', 'Could not load the YouTube player.'), 'error');
        };
        document.head.appendChild(tag);
    }

    function _createPlayer(item) {
        player = new YT.Player('okapi-music-video-mount', {
            width: '100%',
            height: '100%',
            playerVars: { autoplay: 1, playsinline: 1, rel: 0, modestbranding: 1 },
            events: {
                onReady: function () {
                    playerReady = true;
                    player.setVolume(volume);
                    _loadItem(pendingItem || item);
                    pendingItem = null;
                },
                onStateChange: _onPlayerState,
                onError: _onPlayerError,
            }
        });
    }

    function _loadItem(item) {
        if (!item || !player || !playerReady) return;
        if (item.kind === 'playlist') {
            player.loadPlaylist({ list: item.id, listType: 'playlist' });
        } else {
            player.loadVideoById(item.id);
        }
        player.setVolume(volume);
        _renderTrack(item.title);
        _setStatus(_t('music.connecting', 'Connecting…'), '');
    }

    function playYouTube(index) {
        if (!queue.length) {
            _setStatus(_t('music.queue_empty', 'Paste a YouTube link to start a queue.'), '');
            return;
        }
        pausedByPanel = false;
        queueIndex = (index == null || index < 0 || index >= queue.length) ? 0 : index;
        const item = queue[queueIndex];
        _renderQueue();
        _setPlaying(true);
        _setStatus(_t('music.connecting', 'Connecting…'), '');

        if (player && playerReady) { _loadItem(item); return; }
        pendingItem = item;
        _loadIframeApi(function () {
            if (player) { playerReady = true; _loadItem(pendingItem); pendingItem = null; }
            else _createPlayer(pendingItem);
        });
    }

    function _onPlayerState(e) {
        if (e.data === YT.PlayerState.PLAYING) {
            const item = queue[queueIndex];
            let title = (item && item.title) || '';
            // The player knows the real title of the item actually on screen —
            // which for a playlist is the current entry, not the playlist name.
            try {
                const data = player.getVideoData && player.getVideoData();
                if (data && data.title) title = data.title;
            } catch (err) { /* not available yet */ }
            _renderTrack(title);
            _setStatus(_t('music.now_playing', 'Now playing: {s}').replace('{s}', title), 'ok');
            _setPlaying(true);
        } else if (e.data === YT.PlayerState.ENDED) {
            _advance();
        } else if (e.data === YT.PlayerState.PAUSED) {
            _setPlaying(false);
        }
    }

    function _onPlayerError(e) {
        // 101/150 = the uploader disabled embedding; 100 = removed/private;
        // 2 = malformed id; 5 = HTML5 player error.
        const code = e && e.data;
        const message = (code === 101 || code === 150)
            ? _t('music.yt_no_embed', 'That item cannot be played outside YouTube. Skipping.')
            : _t('music.yt_unavailable', 'That item is unavailable. Skipping.');
        _setStatus(message, 'error');
        clearTimeout(skipTimer);
        skipTimer = setTimeout(function () {
            if (queue.length > 1) _advance(); else stopAll();
        }, SKIP_AFTER_ERROR_MS);
    }

    /** Move on after an item finishes, honouring loop + shuffle. */
    function _advance() {
        if (loopMode === 'one') { playYouTube(queueIndex); return; }
        if (shuffle && queue.length > 1) {
            let next = queueIndex;
            while (next === queueIndex) next = Math.floor(Math.random() * queue.length);
            playYouTube(next);
            return;
        }
        const next = queueIndex + 1;
        if (next < queue.length) { playYouTube(next); return; }
        if (loopMode === 'all') { playYouTube(0); return; }
        stopAll();
        _setStatus(_t('music.queue_done', 'Queue finished.'), '');
    }

    /** Manual skip. `wrap` lets the buttons cycle past the ends. */
    function step(delta, wrap) {
        if (source !== 'youtube' || !queue.length) return;
        let next = queueIndex + delta;
        if (next < 0) next = wrap ? queue.length - 1 : 0;
        if (next >= queue.length) next = wrap ? 0 : queue.length - 1;
        playYouTube(next);
    }

    // ── Shared transport ─────────────────────────────────────────────────────

    function play() {
        if (!navigator.onLine) {
            _setStatus(_t('music.offline', 'No internet connection — music is unavailable.'), 'error');
            return;
        }
        if (source === 'youtube') playYouTube(queueIndex >= 0 ? queueIndex : 0);
        else playRadio();
    }

    function stopAll(silent) {
        _clearConnectTimer();
        pausedByPanel = false;
        clearTimeout(skipTimer);
        connected = false;
        if (audio) {
            audio.removeEventListener('error', _radioFailed);
            audio.pause();
            // Detach the source or the browser keeps the connection open and
            // keeps buffering a stream nobody is listening to.
            audio.removeAttribute('src');
            try { audio.load(); } catch (e) { /* teardown only */ }
            audio = null;
        }
        if (player && playerReady) {
            try { player.stopVideo(); } catch (e) { /* already gone */ }
        }
        _setPlaying(false);
        if (!silent) _setStatus('', '');
    }

    function isPlaying() {
        if (audio) return true;
        if (player && playerReady) {
            try { return player.getPlayerState() === YT.PlayerState.PLAYING; } catch (e) { return false; }
        }
        return false;
    }

    function toggle() {
        if (isPlaying()) stopAll(); else play();
    }

    function setSource(next) {
        if (next !== 'radio' && next !== 'youtube') return;
        if (next === source) return;
        stopAll(true);
        source = next;
        _saveSettings({ music_source: source });
        _renderSource();
        _setStatus('', '');
    }

    function selectStation(id) {
        if (!_station(id)) return;
        const wasPlaying = isPlaying();
        currentId = id;
        _renderStation();
        _saveSettings({ music_station: id });
        if (wasPlaying) playRadio();
    }

    function setVolume(v) {
        volume = Math.max(0, Math.min(100, isNaN(v) ? 40 : v));
        if (audio) audio.volume = volume / 100;
        if (player && playerReady) { try { player.setVolume(volume); } catch (e) { /* not ready */ } }
        _renderVolume();
        _saveSettings({ music_volume: volume });
    }

    function cycleLoopMode() {
        loopMode = loopMode === 'all' ? 'one' : (loopMode === 'one' ? 'off' : 'all');
        _renderModes();
        _saveSettings({ music_loop_mode: loopMode });
    }

    function toggleShuffle() {
        shuffle = !shuffle;
        _renderModes();
        _saveSettings({ music_shuffle: shuffle });
    }

    // ── Queue ────────────────────────────────────────────────────────────────

    async function addFromInput() {
        const input = document.getElementById('okapi-music-add-input');
        if (!input) return;
        const ref = input.value.trim();
        if (!ref) return;
        _setStatus(_t('music.adding', 'Adding…'), '');

        const res = await fetch('/music/queue/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ref: ref })
        }).then(r => r.json()).catch(() => null);

        if (!res || res.status !== 'success') {
            _setStatus(_t('music.add_failed', 'That is not a YouTube video or playlist link.'), 'error');
            return;
        }
        input.value = '';
        queue = res.queue || [];
        _renderQueue();
        _setStatus(_t('music.added', 'Added: {s}').replace('{s}', res.item.title), 'ok');
        // First item added to an idle queue starts playing — that is what the
        // user meant by pasting it.
        if (!isPlaying() && queue.length === 1) playYouTube(0);
    }

    function playIndex(i) {
        if (isNaN(i)) return;
        playYouTube(i);
    }

    function removeAt(i) {
        if (isNaN(i) || i < 0 || i >= queue.length) return;
        const wasCurrent = i === queueIndex;
        queue.splice(i, 1);
        if (i < queueIndex) queueIndex -= 1;
        else if (wasCurrent) queueIndex = Math.min(queueIndex, queue.length - 1);
        _saveQueue();
        _renderQueue();
        if (wasCurrent) {
            if (queue.length) playYouTube(queueIndex < 0 ? 0 : queueIndex);
            else stopAll();
        }
    }

    function clearQueue() {
        queue = [];
        queueIndex = -1;
        _saveQueue();
        _renderQueue();
        stopAll();
    }

    // ── Panel ────────────────────────────────────────────────────────────────

    function openPanel() {
        const p = document.getElementById('okapi-music-panel');
        if (!p) return;
        p.classList.remove('okapi-music-hidden');
        panelOpen = true;
        if (pausedByPanel && player && playerReady) {
            pausedByPanel = false;
            try { player.playVideo(); } catch (e) { /* player went away */ }
        }
        if (!navigator.onLine) {
            _setStatus(_t('music.offline', 'No internet connection — music is unavailable.'), 'error');
        }
    }

    function closePanel() {
        // A hidden iframe that keeps playing would break the visible-player
        // requirement, so the panel closing pauses YouTube. Radio keeps going —
        // background audio is the entire point there, and there is nothing to
        // see. Reopening resumes exactly where it left off.
        if (source === 'youtube' && player && playerReady && isPlaying()) {
            try { player.pauseVideo(); pausedByPanel = true; } catch (e) { /* already gone */ }
        }
        const p = document.getElementById('okapi-music-panel');
        if (p) p.classList.add('okapi-music-hidden');
        panelOpen = false;
    }

    function togglePanel() {
        if (panelOpen) closePanel(); else openPanel();
    }

    // ── Mount / unmount ──────────────────────────────────────────────────────

    function unmount() {
        stopAll(true);
        if (player) {
            try { player.destroy(); } catch (e) { /* teardown only */ }
            player = null;
            playerReady = false;
        }
        const root = document.getElementById('okapi-music');
        if (root) root.remove();
        mounted = false;
        panelOpen = false;
    }

    async function refresh() {
        const enabled = (typeof USER_SETTINGS !== 'undefined') && !!USER_SETTINGS.music_enabled;
        if (!enabled) {
            if (mounted) unmount();
            return;
        }

        // The browser's own verdict is checked first: it is free and it is the
        // only one that is definitive when it says "offline".
        if (!navigator.onLine) {
            if (mounted) unmount();
            return;
        }

        const info = await fetch('/music/stations').then(r => r.json()).catch(() => null);
        if (!info || info.status !== 'success' || !info.enabled || !info.online) {
            if (mounted) unmount();
            return;
        }

        stations = info.stations || [];
        if (!stations.length) { if (mounted) unmount(); return; }
        currentId = _station(info.current) ? info.current : stations[0].id;
        volume = Math.max(0, Math.min(100, parseInt(info.volume, 10) || 40));
        source = info.source === 'youtube' ? 'youtube' : 'radio';
        loopMode = ['off', 'one', 'all'].indexOf(info.loop_mode) >= 0 ? info.loop_mode : 'all';
        shuffle = !!info.shuffle;
        queue = Array.isArray(info.queue) ? info.queue : [];

        if (!mounted) {
            _buildDom();
            mounted = true;
        } else {
            _renderSource();
            _renderQueue();
            _renderModes();
        }
    }

    function init() {
        refresh();
        // Losing the network mid-run must not leave a dead widget behind, and
        // regaining it should bring the widget back without a reload.
        window.addEventListener('offline', function () {
            if (mounted) unmount();
        });
        window.addEventListener('online', function () { refresh(); });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Settings save calls refresh() so toggling the feature takes effect now.
    window.OkapiMusic = { refresh, play, stop: stopAll, toggle, isPlaying, unmount };
})();
