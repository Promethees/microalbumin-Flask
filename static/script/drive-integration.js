/**
 * Google Drive Integration Module for Easy OKAPI
 * Handles OAuth authentication, folder selection, and file synchronization
 */

// Check Drive status on page load
$(document).ready(function () {
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
                Swal.fire({
                    icon: 'success',
                    title: 'Connected!',
                    text: 'Successfully connected to Google Drive',
                    timer: 2000,
                    showConfirmButton: false
                });
            }, 500);
        }
    });
}

/**
 * Check Google Drive authentication status and update UI
 */
function checkDriveStatus() {
    $.get('/auth/google/status', function (response) {
        if (response.status === 'success') {
            updateDriveUI(response);

            // If authenticated and folder selected, show sync controls
            if (response.authenticated && response.folder_id) {
                $('#drive-sync-section').removeClass('hidden');
                updateLastSyncTime(response.last_sync);
            }
        }
    }).fail(function (xhr) {
        console.error('Failed to check Drive status:', xhr.responseJSON);
    });
}

/**
 * Initiate Google Drive OAuth flow
 */
function connectGoogleDrive() {
    $.get('/auth/google', function (response) {
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
    }).fail(function (xhr) {
        Swal.fire({
            icon: 'error',
            title: 'Error',
            text: xhr.responseJSON?.message || 'Failed to connect to Google Drive'
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
            $.post('/auth/google/logout', function (response) {
                if (response.status === 'success') {
                    updateDriveUI({ mode: 'guest', authenticated: false });
                    Swal.fire('Disconnected', 'You are now in Guest Mode', 'success');
                }
            }).fail(function (xhr) {
                Swal.fire('Error', xhr.responseJSON?.message || 'Failed to disconnect', 'error');
            });
        }
    });
}

/**
 * Toggle between existing folder and new folder UI
 */
function toggleFolderChoice() {
    const choice = $('input[name="folder-choice"]:checked').val();

    if (choice === 'existing') {
        $('#existing-folder-select').removeClass('hidden');
        $('#new-folder-create').addClass('hidden');
        refreshFolderList();
    } else {
        $('#existing-folder-select').addClass('hidden');
        $('#new-folder-create').removeClass('hidden');
    }
}

/**
 * Refresh the list of Drive folders
 */
function refreshFolderList() {
    $('#drive-folder-dropdown').html('<option value="">Loading folders...</option>');

    $.get('/drive/folders/list', function (response) {
        if (response.status === 'success') {
            const dropdown = $('#drive-folder-dropdown');
            dropdown.empty();
            dropdown.append('<option value="">Select a folder...</option>');

            response.folders.forEach(folder => {
                dropdown.append(`<option value="${folder.id}">${folder.name}</option>`);
            });
        }
    }).fail(function (xhr) {
        Swal.fire('Error', 'Failed to load folders', 'error');
    });
}

/**
 * Select a Drive folder for storage
 */
function selectDriveFolder() {
    const folderId = $('#drive-folder-dropdown').val();
    const folderName = $('#drive-folder-dropdown option:selected').text();

    if (!folderId) return;

    $.post('/drive/folder/select',
        JSON.stringify({ folder_id: folderId, folder_name: folderName }),
        function (response) {
            if (response.status === 'success') {
                $('#selected-folder-display').removeClass('hidden');
                $('#current-folder-name').text(folderName);
                $('#drive-sync-section').removeClass('hidden');
                Swal.fire('Folder Selected', `Using folder: ${folderName}`, 'success');
            }
        },
        'json'
    ).fail(function (xhr) {
        Swal.fire('Error', 'Failed to select folder', 'error');
    });
}

/**
 * Create a new Drive folder
 */
function createDriveFolder() {
    const folderName = $('#new-folder-name').val() || 'Easy OKAPI Data';

    $.post('/drive/folder/create',
        JSON.stringify({ folder_name: folderName }),
        function (response) {
            if (response.status === 'success') {
                const folder = response.folder;
                // Auto-select the newly created folder
                $.post('/drive/folder/select',
                    JSON.stringify({ folder_id: folder.id, folder_name: folder.name }),
                    function (selectResponse) {
                        if (selectResponse.status === 'success') {
                            $('#selected-folder-display').removeClass('hidden');
                            $('#current-folder-name').text(folder.name);
                            $('#drive-sync-section').removeClass('hidden');
                            Swal.fire('Folder Created', `Created and selected: ${folder.name}`, 'success');
                        }
                    },
                    'json'
                );
            }
        },
        'json'
    ).fail(function (xhr) {
        Swal.fire('Error', 'Failed to create folder', 'error');
    });
}

/**
 * Sync session data to Drive
 */
function syncToDrive() {
    Swal.fire({
        title: 'Syncing to Drive...',
        text: 'Uploading your data',
        allowOutsideClick: false,
        didOpen: () => {
            Swal.showLoading();
        }
    });

    $.post('/drive/sync', function (response) {
        Swal.close();

        if (response.status === 'success') {
            updateLastSyncTime(new Date().toISOString());
            Swal.fire({
                icon: 'success',
                title: 'Sync Complete',
                text: response.message,
                timer: 2000
            });
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
    }).fail(function (xhr) {
        Swal.close();
        Swal.fire('Error', xhr.responseJSON?.message || 'Sync failed', 'error');
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
            Swal.fire({
                title: 'Loading from Drive...',
                text: 'Downloading your data',
                allowOutsideClick: false,
                didOpen: () => {
                    Swal.showLoading();
                }
            });

            $.post('/drive/load', function (response) {
                Swal.close();

                if (response.status === 'success') {
                    Swal.fire({
                        icon: 'success',
                        title: 'Load Complete',
                        text: response.message,
                        timer: 2000
                    });
                    // Refresh file tables
                    location.reload();
                } else {
                    Swal.fire({
                        icon: 'error',
                        title: 'Load Failed',
                        text: response.message
                    });
                }
            }).fail(function (xhr) {
                Swal.close();
                Swal.fire('Error', xhr.responseJSON?.message || 'Load failed', 'error');
            });
        }
    });
}

/**
 * Update auto-sync preference
 */
function updateAutoSyncPreference() {
    const enabled = $('#auto-sync-checkbox').is(':checked');

    $.post('/drive/preferences/set',
        JSON.stringify({ key: 'auto_sync_on_close', value: enabled }),
        function (response) {
            if (response.status === 'success') {
                console.log('Auto-sync preference updated:', enabled);
            }
        },
        'json'
    );
}

/**
 * Setup beforeunload handler for auto-sync
 */
function setupBeforeUnloadHandler() {
    window.addEventListener('beforeunload', function (e) {
        // Check if auto-sync is enabled
        $.get('/drive/preferences/get', function (response) {
            if (response.status === 'success' && response.preferences.auto_sync_on_close) {
                // Trigger sync (note: this may not complete before page unloads)
                $.post('/drive/sync');
            }
        });
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
        $('#drive-connect-btn').addClass('hidden');
        $('#drive-disconnect-btn').removeClass('hidden');
        $('#drive-folder-section').removeClass('hidden');

        // If folder selected, show it
        if (status.folder_name) {
            $('#selected-folder-display').removeClass('hidden');
            $('#current-folder-name').text(status.folder_name);
        }

        // Update auto-sync checkbox
        $('#auto-sync-checkbox').prop('checked', status.auto_sync_on_close || false);
    } else {
        $('#drive-connect-btn').removeClass('hidden');
        $('#drive-disconnect-btn').addClass('hidden');
        $('#drive-folder-section').addClass('hidden');
        $('#drive-sync-section').addClass('hidden');
    }
}

/**
 * Update mode indicator badge
 */
function updateModeIndicator(mode) {
    const badge = $('#drive-mode-badge');
    const description = $('#drive-mode-description');

    if (mode === 'connected') {
        badge.removeClass('badge-guest').addClass('badge-connected');
        badge.text('Connected');
        description.text('Syncing to Google Drive');
    } else {
        badge.removeClass('badge-connected').addClass('badge-guest');
        badge.text('Guest Mode');
        description.text('Data will not be saved');
    }
}

/**
 * Update last sync time display
 */
function updateLastSyncTime(isoString) {
    if (!isoString) {
        $('#last-sync-time').text('Never');
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

    $('#last-sync-time').text(timeText);
    $('#last-sync-info').removeClass('hidden');
}
