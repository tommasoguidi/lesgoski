// webapp/static/scripts.js

// ==========================================
// PASSWORD VISIBILITY TOGGLE
// ==========================================

function togglePasswordVisibility(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    input.type = input.type === 'password' ? 'text' : 'password';
}

// ==========================================
// BROSKI USERNAME AUTOCOMPLETE
// ==========================================

function initBroskiAutocomplete(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;

    const wrapper = input.parentElement;
    wrapper.style.position = 'relative';

    // Create dropdown (reuse airport-dropdown styling)
    const dropdown = document.createElement('div');
    dropdown.className = 'airport-dropdown';
    wrapper.appendChild(dropdown);

    let selecting = false;

    input.addEventListener('input', async () => {
        const query = input.value.trim();
        if (query.length < 2) {
            dropdown.innerHTML = '';
            dropdown.style.display = 'none';
            return;
        }

        try {
            const res = await fetch(`/api/users/search?q=${encodeURIComponent(query)}`);
            const users = await res.json();

            dropdown.innerHTML = '';
            if (users.length === 0) {
                dropdown.style.display = 'none';
                return;
            }

            users.forEach(u => {
                const item = document.createElement('div');
                item.className = 'airport-dropdown-item';
                item.textContent = u.username;
                item.addEventListener('mousedown', () => { selecting = true; });
                item.addEventListener('click', (e) => {
                    e.preventDefault();
                    input.value = u.username;
                    dropdown.innerHTML = '';
                    dropdown.style.display = 'none';
                    selecting = false;
                });
                dropdown.appendChild(item);
            });
            dropdown.style.display = 'block';
        } catch (err) {
            console.error('Broski search failed:', err);
            dropdown.style.display = 'none';
        }
    });

    input.addEventListener('blur', () => {
        setTimeout(() => {
            if (!selecting) {
                dropdown.style.display = 'none';
            }
            selecting = false;
        }, 150);
    });
}

// ==========================================
// DEALS PAGE — Filters
// ==========================================

function toggleFilters() {
    const sheet = document.getElementById('filterSheet');
    const trigger = document.getElementById('filterTrigger');
    const backdrop = document.getElementById('sheetBackdrop');

    sheet.classList.toggle('active');
    trigger.classList.toggle('hidden');
    backdrop.classList.toggle('active');
}

function toggleAllCountries(state) {
    const checkboxes = document.querySelectorAll('.country-filter');
    checkboxes.forEach(cb => cb.checked = state);
    applyFilters();
}

function applyFilters() {
    const destInput = document.getElementById('filterDest');
    if (!destInput) return;
    const query = destInput.value.toLowerCase();

    const checkedCountries = new Set(
        Array.from(document.querySelectorAll('.country-filter:checked')).map(cb => cb.value)
    );

    const cards = document.querySelectorAll('.deal-card');
    let visible = 0;

    cards.forEach(card => {
        const cardDest = card.getAttribute('data-dest').toLowerCase();
        const cardCountry = card.getAttribute('data-country');

        const matchesDest = query === '' || cardDest.includes(query);
        const matchesCountry = checkedCountries.has(cardCountry);

        if (matchesDest && matchesCountry) {
            card.style.display = 'block';
            visible++;
        } else {
            card.style.display = 'none';
        }
    });

    const counter = document.getElementById('visibleCount');
    if (counter) counter.innerText = visible;

    const noDealsMsg = document.getElementById('noDealsMsg');
    if (noDealsMsg) noDealsMsg.style.display = (visible === 0) ? 'block' : 'none';
}

document.addEventListener('DOMContentLoaded', () => {
    applyFilters();
    initDealsAirportFilter('filterDest');
});

function triggerUpdate(btn, profileId) {
    const icon = btn.querySelector('.refresh-icon');
    icon.classList.add('spinning');
    btn.disabled = true;

    fetch(`/update/${profileId}`, { method: 'POST' })
        .then(res => {
            if (res.ok) window.location.reload();
            else {
                alert("Update failed");
                icon.classList.remove('spinning');
                btn.disabled = false;
            }
        });
}


// ==========================================
// DEALS PAGE — Airport Autocomplete Filter
// ==========================================

function initDealsAirportFilter(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;

    const wrapper = input.parentElement;
    wrapper.style.position = 'relative';

    // Create dropdown
    const dropdown = document.createElement('div');
    dropdown.className = 'airport-dropdown';
    wrapper.appendChild(dropdown);

    let selecting = false;

    input.addEventListener('input', async () => {
        const query = input.value.trim().toLowerCase();
        // Still apply text filter even if not selecting from dropdown
        applyFilters();

        if (query.length < 2) {
            dropdown.innerHTML = '';
            dropdown.style.display = 'none';
            return;
        }

        const airports = await loadAirports();
        const matches = airports.filter(a =>
            a.iata.toLowerCase().includes(query) ||
            a.name.toLowerCase().includes(query) ||
            a.city.toLowerCase().includes(query)
        ).slice(0, 8);

        dropdown.innerHTML = '';
        if (matches.length === 0) {
            dropdown.style.display = 'none';
            return;
        }

        matches.forEach(a => {
            const item = document.createElement('div');
            item.className = 'airport-dropdown-item';
            item.textContent = `${a.iata} - ${a.city} (${a.name})`;
            item.addEventListener('mousedown', () => { selecting = true; });
            item.addEventListener('click', (e) => {
                e.preventDefault();
                input.value = a.iata;
                dropdown.innerHTML = '';
                dropdown.style.display = 'none';
                selecting = false;
                applyFilters();
            });
            dropdown.appendChild(item);
        });
        dropdown.style.display = 'block';
    });

    input.addEventListener('blur', () => {
        setTimeout(() => {
            if (!selecting) {
                dropdown.style.display = 'none';
            }
            selecting = false;
        }, 150);
    });

    // Remove the old onkeyup handler since we handle it via 'input' event
    input.removeAttribute('onkeyup');
}


// ==========================================
// PROFILE FORM — Airport Autocomplete
// ==========================================

let _airportCache = null;

async function loadAirports() {
    if (_airportCache) return _airportCache;
    const res = await fetch('/api/airports');
    _airportCache = await res.json();
    return _airportCache;
}

function initAirportInput(inputId, hiddenId) {
    const input = document.getElementById(inputId);
    const hidden = document.getElementById(hiddenId);
    if (!input || !hidden) return;

    const wrapper = input.parentElement;
    wrapper.style.position = 'relative';

    // Create chips container
    const chips = document.createElement('div');
    chips.className = 'airport-chips';
    wrapper.insertBefore(chips, input);

    // Create dropdown
    const dropdown = document.createElement('div');
    dropdown.className = 'airport-dropdown';
    wrapper.appendChild(dropdown);

    // Flag to prevent blur from hiding dropdown during selection
    let selecting = false;

    // Load initial values from hidden field, then clear it so addChip can rebuild
    const initial = hidden.value.split(',').filter(v => v.trim());
    hidden.value = '';
    initial.forEach(code => addChip(code.trim(), chips, hidden));

    input.addEventListener('input', async () => {
        const query = input.value.trim().toLowerCase();
        if (query.length < 2) {
            dropdown.innerHTML = '';
            dropdown.style.display = 'none';
            return;
        }

        const airports = await loadAirports();
        const matches = airports.filter(a =>
            a.iata.toLowerCase().includes(query) ||
            a.name.toLowerCase().includes(query) ||
            a.city.toLowerCase().includes(query)
        ).slice(0, 8);

        dropdown.innerHTML = '';
        if (matches.length === 0) {
            dropdown.style.display = 'none';
            return;
        }

        matches.forEach(a => {
            const item = document.createElement('div');
            item.className = 'airport-dropdown-item';
            item.textContent = `${a.iata} - ${a.city} (${a.name})`;
            item.addEventListener('mousedown', () => {
                selecting = true;
            });
            item.addEventListener('click', (e) => {
                e.preventDefault();
                addChip(a.iata, chips, hidden);
                input.value = '';
                dropdown.innerHTML = '';
                dropdown.style.display = 'none';
                selecting = false;
                input.focus();
            });
            dropdown.appendChild(item);
        });
        dropdown.style.display = 'block';
    });

    input.addEventListener('blur', () => {
        setTimeout(() => {
            if (!selecting) {
                dropdown.style.display = 'none';
            }
            selecting = false;
        }, 150);
    });
}

function addChip(code, chipsContainer, hiddenInput) {
    const current = hiddenInput.value.split(',').filter(v => v.trim());
    if (current.includes(code)) return;

    const chip = document.createElement('span');
    chip.className = 'airport-chip';
    chip.innerHTML = `${code} <span class="chip-remove">&times;</span>`;

    // Use event listener instead of inline onclick for robustness
    chip.querySelector('.chip-remove').addEventListener('click', () => {
        chip.remove();
        const updated = hiddenInput.value.split(',').filter(v => v.trim() && v.trim() !== code);
        hiddenInput.value = updated.join(',');
    });

    chipsContainer.appendChild(chip);
    current.push(code);
    hiddenInput.value = current.join(',');
}


// ==========================================
// PROFILE FORM — Strategy Editor (noUiSlider)
// ==========================================

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function initStrategyEditor() {
    const editor = document.getElementById('strategy-editor');
    if (!editor) return;

    const hiddenField = document.getElementById('strategy-json-hidden');
    const dataStr = editor.getAttribute('data-strategy');

    // Parse existing strategy (edit mode) or use defaults
    let existing = null;
    if (dataStr) {
        try { existing = JSON.parse(dataStr); } catch (e) { /* use defaults */ }
    }

    // Build outbound section - no days selected by default
    buildDaySection(editor, 'out', 'Outbound Departure', existing ? existing.out_days : {});

    // Build inbound section - no days selected by default
    buildDaySection(editor, 'in', 'Return Departure', existing ? existing.in_days : {});

    // Build stay duration section
    const staySection = document.createElement('div');
    staySection.className = 'strategy-section';
    staySection.innerHTML = `
        <label class="form-label text-white fw-bold">Stay Duration</label>
        <div class="d-flex align-items-center gap-3">
            <div class="d-flex align-items-center gap-2">
                <span class="text-muted small">Min nights</span>
                <input type="number" id="min-nights" class="form-control form-control-sm strategy-number-input"
                       min="0" max="30" value="${existing ? existing.min_nights : 1}">
            </div>
            <div class="d-flex align-items-center gap-2">
                <span class="text-muted small">Max nights</span>
                <input type="number" id="max-nights" class="form-control form-control-sm strategy-number-input"
                       min="0" max="30" value="${existing ? existing.max_nights : 2}">
            </div>
        </div>
    `;
    editor.appendChild(staySection);

    // Listen for changes on number inputs
    editor.addEventListener('change', () => syncStrategyJson());
    editor.addEventListener('input', () => syncStrategyJson());

    // Initial sync
    syncStrategyJson();
}

function buildDaySection(container, prefix, label, activeDays) {
    const section = document.createElement('div');
    section.className = 'strategy-section mb-3';

    // Label
    const labelEl = document.createElement('label');
    labelEl.className = 'form-label text-white fw-bold';
    labelEl.textContent = label;
    section.appendChild(labelEl);

    // Day toggle buttons
    const btnGroup = document.createElement('div');
    btnGroup.className = 'd-flex flex-wrap gap-2 mb-2';

    // Time rows container
    const timeRows = document.createElement('div');
    timeRows.id = `${prefix}-time-rows`;

    for (let i = 0; i < 7; i++) {
        const isActive = activeDays && (i.toString() in activeDays || i in activeDays);
        const timeWindow = isActive ? (activeDays[i] || activeDays[i.toString()]) : [0, 24];

        // Day toggle button
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `btn btn-sm ${isActive ? 'btn-primary' : 'btn-outline-secondary'} strategy-day-btn`;
        btn.textContent = DAY_NAMES[i];
        btn.dataset.day = i;
        btn.dataset.prefix = prefix;
        btn.dataset.active = isActive ? '1' : '0';

        btn.addEventListener('click', () => {
            const nowActive = btn.dataset.active === '1';
            btn.dataset.active = nowActive ? '0' : '1';
            btn.className = `btn btn-sm ${nowActive ? 'btn-outline-secondary' : 'btn-primary'} strategy-day-btn`;
            const row = document.getElementById(`${prefix}-time-${i}`);
            row.style.display = nowActive ? 'none' : 'flex';
            syncStrategyJson();
        });

        btnGroup.appendChild(btn);

        // Time window row with noUiSlider
        const row = document.createElement('div');
        row.id = `${prefix}-time-${i}`;
        row.className = 'strategy-time-row';
        row.style.display = isActive ? 'flex' : 'none';

        const dayLabel = document.createElement('span');
        dayLabel.className = 'strategy-day-label';
        dayLabel.textContent = DAY_NAMES[i];

        const rangeLabel = document.createElement('span');
        rangeLabel.className = 'range-value';
        rangeLabel.id = `${prefix}-label-${i}`;
        rangeLabel.textContent = `${timeWindow[0]}:00 – ${timeWindow[1]}:00`;

        const sliderWrap = document.createElement('div');
        sliderWrap.className = 'nouislider-wrap';

        const sliderEl = document.createElement('div');
        sliderEl.id = `${prefix}-slider-${i}`;
        sliderWrap.appendChild(sliderEl);

        row.appendChild(dayLabel);
        row.appendChild(rangeLabel);
        row.appendChild(sliderWrap);
        timeRows.appendChild(row);

        // Initialize noUiSlider synchronously so syncStrategyJson() can read values
        noUiSlider.create(sliderEl, {
            start: [timeWindow[0], timeWindow[1]],
            connect: true,
            step: 1,
            range: { min: 0, max: 24 },
            format: {
                to: v => Math.round(v),
                from: v => Number(v)
            }
        });

        sliderEl.noUiSlider.on('update', (values) => {
            const f = values[0];
            const t = values[1];
            rangeLabel.textContent = `${f}:00 – ${t}:00`;
        });

        sliderEl.noUiSlider.on('change', () => {
            syncStrategyJson();
        });
    }

    section.appendChild(btnGroup);
    section.appendChild(timeRows);
    container.appendChild(section);
}

function syncStrategyJson() {
    const hiddenField = document.getElementById('strategy-json-hidden');
    if (!hiddenField) return;

    const outDays = {};
    const inDays = {};

    for (let i = 0; i < 7; i++) {
        // Outbound
        const outBtn = document.querySelector(`[data-prefix="out"][data-day="${i}"]`);
        if (outBtn && outBtn.dataset.active === '1') {
            const slider = document.getElementById(`out-slider-${i}`);
            if (slider && slider.noUiSlider) {
                const vals = slider.noUiSlider.get();
                outDays[i] = [vals[0], vals[1]];
            }
        }

        // Inbound
        const inBtn = document.querySelector(`[data-prefix="in"][data-day="${i}"]`);
        if (inBtn && inBtn.dataset.active === '1') {
            const slider = document.getElementById(`in-slider-${i}`);
            if (slider && slider.noUiSlider) {
                const vals = slider.noUiSlider.get();
                inDays[i] = [vals[0], vals[1]];
            }
        }
    }

    const minNights = parseInt(document.getElementById('min-nights').value) || 0;
    const maxNights = parseInt(document.getElementById('max-nights').value) || 0;

    const strategy = {
        out_days: outDays,
        in_days: inDays,
        min_nights: minNights,
        max_nights: maxNights
    };

    hiddenField.value = JSON.stringify(strategy);
}


// ==========================================
// DEALS PAGE — Notification Bell Toggle
// ==========================================

function toggleNotification(btn, profileId, destination) {
    fetch('/api/notify-toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            profile_id: profileId,
            destination: destination
        })
    })
    .then(res => res.json())
    .then(data => {
        const icon = btn.querySelector('.bell-icon');
        if (data.enabled) {
            icon.innerHTML = '\u{1F514}';
            icon.className = 'bell-icon bell-active';
        } else {
            icon.innerHTML = '\u{1F515}';
            icon.className = 'bell-icon bell-inactive';
        }
    })
    .catch(err => {
        console.error('Failed to toggle notification:', err);
    });
}


// ==========================================
// CLIPBOARD / SHARE UTILITIES
// ==========================================

function copyToClipboard(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
        const orig = btn.innerHTML;
        btn.innerHTML = 'Copied!';
        btn.classList.replace('btn-outline-secondary', 'btn-success');
        setTimeout(() => {
            btn.innerHTML = orig;
            btn.classList.replace('btn-success', 'btn-outline-secondary');
        }, 2000);
    });
}

function shareInviteLink(url) {
    if (navigator.share) {
        navigator.share({
            title: 'Join Lesgoski',
            text: "You've been invited to Lesgoski — a personal flight deal tracker.",
            url: url
        }).catch(() => {});
    } else {
        navigator.clipboard.writeText(url).then(() => alert('Invite link copied to clipboard:\n' + url));
    }
}


// ==========================================
// SIGNUP — Live Username Availability
// ==========================================

function initUsernameValidator(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    let timer;
    input.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(async () => {
            const val = input.value.trim();
            input.classList.remove('is-valid', 'is-invalid');
            if (val.length < 3) return;
            try {
                const res = await fetch(`/api/username-available?username=${encodeURIComponent(val)}`);
                const { available } = await res.json();
                if (available === true) input.classList.add('is-valid');
                else if (available === false) input.classList.add('is-invalid');
            } catch (e) {}
        }, 400);
    });
}
