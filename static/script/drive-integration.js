/**
 * Google Drive Integration Module for Easy OKAPI
 * Handles OAuth authentication, folder selection, and file synchronization
 */

// Check Drive status on page load
window.addEventListener('load', function () {
    // Skip all Drive initialisation for logged-in users — Firebase handles persistence
    if (typeof IS_LOGGED_IN !== 'undefined' && IS_LOGGED_IN) return;

    // Check if this is an OAuth callback
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('code') && urlParams.has('state')) {
        // This is an OAuth callback, handle it
        handleOAuthCallback();
    } else {
        // Normal page load
        checkDriveStatus();
    }

    setupBeforeUnloadHandler();
    setupOAuthMessageListener();
});

/**
 * Setup message listener for OAuth popup communication
 */
function setupOAuthMessageListener() {
    window.addEventListener('message', function (event) {
        // Security: verify origin if needed
        // if (event.origin !== window.location.origin) return;

        if (event.data && event.data.type === 'oauth_success') {
            console.log('Received OAuth success message from popup');
            // Update Drive status without page refresh
            setTimeout(() => {
                checkDriveStatus();
                refreshFolderList(); // Automatically load folders after connection

                if (!getBtnChecked("no-swal-checkbox")) {
                    Swal.fire({
                        icon: 'success',
                        title: 'Connected!',
                        text: 'Successfully connected to Google Drive',
                        timer: 2000,
                        showConfirmButton: false
                    });
                } else {
                    console.log('Successfully connected to Google Drive');
                }
            }, 500);
        }
    });
}

/**
 * Check Google Drive authentication status and update UI
 */
function checkDriveStatus() {
    fetchJSON('/auth/google/status')
        .then(response => {
            if (response.status === 'success') {
                updateDriveUI(response);

                // If authenticated and folder selected, show sync controls
                if (response.authenticated && response.folder_id) {
                    $id('drive-sync-section').classList.remove('hidden');
                    updateLastSyncTime(response.last_sync);
                }
            }
        })
        .catch(error => {
            console.error('Failed to check Drive status:', error);
        });
}

/**
 * Initiate Google Drive OAuth flow
 */
function connectGoogleDrive() {
    fetchJSON('/auth/google')
        .then(response => {
            if (response.status === 'success') {
                // Open OAuth URL in popup or redirect
                const width = 600;
                const height = 700;
                const left = (screen.width - width) / 2;
                const top = (screen.height - height) / 2;

                const authWindow = window.open(
                    response.authorization_url,
                    'Google Drive Authentication',
                    `width=${width},height=${height},left=${left},top=${top}`
                );

                // Poll for authentication completion
                const pollTimer = setInterval(function () {
                    if (authWindow.closed) {
                        clearInterval(pollTimer);
                        // Recheck status after auth window closes
                        setTimeout(checkDriveStatus, 1000);
                    }
                }, 500);
            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'Connection Failed',
                    text: response.message || 'Failed to initiate Google Drive connection'
                });
            }
        })
        .catch(error => {
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: error.message || 'Failed to connect to Google Drive'
            });
        });
}

/**
 * Handle OAuth callback (called from popup window)
 * Note: This function is now mainly a fallback or for direct navigation cases.
 * The primary method is via callback.html sending a postMessage.
 */
function handleOAuthCallback() {
    // This function is kept for backward compatibility or direct navigation cases
    // where the server might redirect back with params if we change the flow.
    // For now, the server renders callback.html which handles the messaging.
    console.log("handleOAuthCallback called - checking params");
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('code') && urlParams.has('state')) {
        // In the new flow, the server consumes the code. 
        // If we are here, it means we are on the main page with code params,
        // which shouldn't happen with the popup flow + server render.
        // Unless the user manually navigated here.
        console.log("Code and state present on main page");
        window.history.replaceState({}, document.title, "/");
        checkDriveStatus();
    }
}

/**
 * Disconnect from Google Drive
 */
function disconnectGoogleDrive() {
    Swal.fire({
        title: 'Disconnect Google Drive?',
        text: 'Your session data will remain, but will no longer sync to Drive.',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Disconnect',
        cancelButtonText: 'Cancel'
    }).then((result) => {
        if (result.isConfirmed) {
            fetchJSON('/auth/google/logout', { method: 'POST' })
                .then(response => {
                    if (response.status === 'success') {
                        updateDriveUI({ mode: 'guest', authenticated: false });
                        if (!getBtnChecked("no-swal-checkbox")) {
                            Swal.fire('Disconnected', 'You are now in Guest Mode', 'success');
                        } else {
                            console.log('Disconnected from Google Drive');
                        }
                    }
                    $id("selected-folder-display").classList.add("hidden");
                })
                .catch(error => {
                    Swal.fire('Error', error.message || 'Failed to disconnect', 'error');
                });
        }
    });
}

/**
 * Toggle between existing folder and new folder UI
 */
function toggleFolderChoice() {
    const choice = document.querySelector('input[name="folder-choice"]:checked')?.value;

    if (choice === 'existing') {
        $id('existing-folder-select').classList.remove('hidden');
        $id('new-folder-create').classList.add('hidden');
        refreshFolderList();
    } else {
        $id('existing-folder-select').classList.add('hidden');
        $id('new-folder-create').classList.remove('hidden');
        $id('selected-folder-display').classList.add('hidden');
    }
}

/**
 * Refresh the list of Drive folders
 * @param {string} selectedId - Optional ID of folder to select after loading
 */
function refreshFolderList(selectedId = null) {
    const dropdown = $id('drive-folder-dropdown');
    dropdown.innerHTML = '<option value="">Loading folders...</option>';

    fetchJSON('/drive/folder/list')
        .then(response => {
            if (response.status === 'success') {
                dropdown.innerHTML = '';
                const defaultOption = document.createElement('option');
                defaultOption.value = '';
                defaultOption.textContent = 'Select a folder...';
                dropdown.appendChild(defaultOption);

                response.folders.forEach(folder => {
                    const option = document.createElement('option');
                    option.value = folder.id;
                    option.textContent = folder.name;
                    dropdown.appendChild(option);
                });

                // Auto-select if requested
                if (selectedId) {
                    dropdown.value = selectedId;
                }
            } else {
                Swal.fire('Error', response.message || 'Invalid response format', 'error');
            }
        })
        .catch(error => {
            Swal.fire({
                title: 'Error',
                html: `Failed to load folders<br><br><small>${error.message}</small>`,
                icon: 'error',
                confirmButtonText: 'OK'
            });
        });
}

/**
 * Briefly reveal the "Pull from Drive" hint after a folder is selected,
 * then fade it out so it doesn't linger.
 */
let _folderPullHintTimers = [];
function showFolderPullHint() {
    const hint = $id('folder-pull-hint');
    if (!hint) return;

    // Cancel any in-flight cycle so rapid re-selects restart cleanly.
    _folderPullHintTimers.forEach(clearTimeout);
    _folderPullHintTimers = [];

    hint.classList.remove('hidden', 'folder-pull-hint--hide', 'folder-pull-hint--show');
    // Force reflow so the entrance animation restarts on repeat selections.
    void hint.offsetWidth;
    hint.classList.add('folder-pull-hint--show');

    _folderPullHintTimers.push(setTimeout(() => {
        // Stop the glow, then fade out.
        hint.classList.remove('folder-pull-hint--show');
        hint.classList.add('folder-pull-hint--hide');
        _folderPullHintTimers.push(setTimeout(() => {
            hint.classList.add('hidden');
            hint.classList.remove('folder-pull-hint--hide');
        }, 450));
    }, 4500));
}

/**
 * Select a Drive folder for storage
 */
function selectDriveFolder() {
    const dropdown = $id('drive-folder-dropdown');
    const folderId = dropdown.value;
    const folderName = dropdown.options[dropdown.selectedIndex]?.text;

    if (!folderId) {
        Swal.fire('Warning', 'Please select a folder first', 'warning');
        return;
    }

    fetchJSON('/drive/folder/select', {
        method: 'POST',
        body: JSON.stringify({
            folder_id: folderId,
            folder_name: folderName
        })
    })
        .then(response => {
            if (response.status === 'success') {
                $id('selected-folder-display').classList.remove('hidden');
                $id('current-folder-name').textContent = folderName;
                $id('drive-sync-section').classList.remove('hidden');
                showFolderPullHint();
                if (!getBtnChecked("no-swal-checkbox")) {
                    Swal.fire({
                        title: 'Success',
                        text: `Using folder: ${folderName}`,
                        icon: 'success',
                        timer: 1800,
                        showConfirmButton: false
                    });
                } else {
                    console.log(`Using folder: ${folderName}`);
                }
            } else {
                Swal.fire('Error', response.message || 'Operation failed', 'error');
            }
        })
        .catch(error => {
            Swal.fire({
                title: 'Error',
                html: `Failed to select folder<br><small>${error.message}</small>`,
                icon: 'error'
            });
        });
}

/**
 * Create a new Drive folder
 */
function createDriveFolder() {
    const folderName = $id('new-folder-name').value || 'Easy OKAPI Data';

    fetchJSON('/drive/folder/create', {
        method: 'POST',
        body: JSON.stringify({ folder_name: folderName })
    })
        .then(response => {
            if (response.status === 'success') {
                const folder = response.folder;
                // Auto-select the newly created folder
                return fetchJSON('/drive/folder/select', {
                    method: 'POST',
                    body: JSON.stringify({ folder_id: folder.id, folder_name: folder.name })
                }).then(selectResponse => {
                    if (selectResponse.status === 'success') {
                        $id('selected-folder-display').classList.remove('hidden');
                        $id('current-folder-name').textContent = folder.name;
                        $id('drive-sync-section').classList.remove('hidden');

                        if (!getBtnChecked("no-swal-checkbox")) {
                            Swal.fire('Folder Created', `Created and selected: ${folder.name}`, 'success');
                        } else {
                            console.log(`Created and selected: ${folder.name}`);
                        }

                        // Return to "Use Existing" mode automatically and select the new folder
                        const existingRadio = document.querySelector('input[name="folder-choice"][value="existing"]');
                        if (existingRadio) existingRadio.checked = true;
                        $id('existing-folder-select').classList.remove('hidden');
                        $id('new-folder-create').classList.add('hidden');
                        refreshFolderList(folder.id);
                    }
                });
            }
        })
        .catch(error => {
            Swal.fire('Error', error.message || 'Failed to create folder', 'error');
        });
}

/**
 * Sync session data to Drive
 */
function syncToDrive() {
    if (typeof window.showSpinner === 'function') window.showSpinner();

    fetchJSON('/drive/sync', { method: 'POST' })
        .then(response => {
            if (typeof window.hideSpinner === 'function') window.hideSpinner();

            if (response.status === 'success') {
                updateLastSyncTime(new Date().toISOString());
                if (!getBtnChecked("no-swal-checkbox")) {
                    Swal.fire({
                        icon: 'success',
                        title: 'Sync Complete',
                        text: response.message,
                        timer: 2000
                    });
                } else {
                    console.log('Sync Complete:', response.message);
                }
            } else if (response.status === 'partial') {
                Swal.fire({
                    icon: 'warning',
                    title: 'Partial Sync',
                    text: response.message,
                    footer: `Errors: ${response.errors.join(', ')}`
                });
            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'Sync Failed',
                    text: response.message
                });
            }
        })
        .catch(error => {
            if (typeof window.hideSpinner === 'function') window.hideSpinner();
            Swal.fire('Error', error.message || 'Sync failed', 'error');
        });
}

/**
 * Load data from Drive to session
 */
function loadFromDrive() {
    Swal.fire({
        title: 'Load from Drive?',
        text: 'This will replace your current session data',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Load',
        cancelButtonText: 'Cancel'
    }).then((result) => {
        if (result.isConfirmed) {
            if (typeof window.showSpinner === 'function') window.showSpinner();

            fetchJSON('/drive/load', { method: 'POST' })
                .then(response => {
                    if (typeof window.hideSpinner === 'function') window.hideSpinner();

                    if (response.status === 'success') {
                        if (!getBtnChecked("no-swal-checkbox")) {
                            Swal.fire({
                                icon: 'success',
                                title: 'Load Complete',
                                text: response.message,
                                timer: 2000,
                                showConfirmButton: false
                            });
                        } else {
                            console.log('Load Complete:', response.message);
                        }
                        // Note: Tables update automatically via socket events
                    } else {
                        Swal.fire({
                            icon: 'error',
                            title: 'Load Failed',
                            text: response.message
                        });
                    }
                })
                .catch(error => {
                    if (typeof window.hideSpinner === 'function') window.hideSpinner();
                    Swal.fire('Error', error.message || 'Load failed', 'error');
                });
        }
    });
}

/**
 * Update auto-sync preference
 */
function updateAutoSyncPreference() {
    const enabled = $id('auto-sync-checkbox').checked;

    fetchJSON('/drive/preferences/set', {
        method: 'POST',
        body: JSON.stringify({ key: 'auto_sync_on_close', value: enabled })
    })
        .then(response => {
            if (response.status === 'success') {
                console.log('Auto-sync preference updated:', enabled);
            }
        })
        .catch(error => console.error('Error updating auto-sync preference:', error));
}

/**
 * Setup beforeunload handler for auto-sync
 */
function setupBeforeUnloadHandler() {
    window.addEventListener('beforeunload', function (e) {
        // Check if auto-sync is enabled
        fetchJSON('/drive/preferences/get')
            .then(response => {
                if (response.status === 'success' && response.preferences.auto_sync_on_close) {
                    // Trigger sync (note: this may not complete before page unloads)
                    fetch('/drive/sync', { method: 'POST' });
                }
            })
            .catch(error => console.error('Error in beforeunload sync check:', error));
    });
}

/**
 * Update Drive UI based on status
 */
function updateDriveUI(status) {
    const mode = status.mode || 'guest';
    const authenticated = status.authenticated || false;

    // Update mode indicator
    updateModeIndicator(mode);

    // Show/hide connection controls
    if (authenticated) {
        $id('drive-connect-btn').classList.add('hidden');
        $id('drive-disconnect-btn').classList.remove('hidden');
        $id('drive-folder-section').classList.remove('hidden');

        // If folder selected, show it
        if (status.folder_name) {
            $id('selected-folder-display').classList.remove('hidden');
            $id('current-folder-name').textContent = status.folder_name;
        }

        // Update auto-sync checkbox
        $id('auto-sync-checkbox').checked = status.auto_sync_on_close || false;
    } else {
        $id('drive-connect-btn').classList.remove('hidden');
        $id('drive-disconnect-btn').classList.add('hidden');
        $id('drive-folder-section').classList.add('hidden');
        $id('drive-sync-section').classList.add('hidden');
    }
}

/**
 * Update mode indicator badge
 */
function updateModeIndicator(mode) {
    const badge = $id('drive-mode-badge');
    const description = $id('drive-mode-description');

    if (mode === 'connected') {
        badge.classList.remove('badge-guest');
        badge.classList.add('badge-connected');
        badge.textContent = 'Connected';
        description.textContent = 'Syncing to Google Drive';
    } else {
        badge.classList.remove('badge-connected');
        badge.classList.add('badge-guest');
        badge.textContent = 'Guest Mode';
        description.textContent = 'Data will not be saved';
    }
}

/**
 * Update last sync time display
 */
function updateLastSyncTime(isoString) {
    const lastSyncTimeEl = $id('last-sync-time');
    if (!isoString) {
        lastSyncTimeEl.textContent = 'Never';
        return;
    }

    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);

    let timeText;
    if (diffMins < 1) {
        timeText = 'Just now';
    } else if (diffMins < 60) {
        timeText = `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
    } else {
        const diffHours = Math.floor(diffMins / 60);
        timeText = `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    }

    lastSyncTimeEl.textContent = timeText;
    $id('last-sync-info').classList.remove('hidden');
}
