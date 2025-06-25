function runScript() {
    const baseDir = $("#base-dir").val() || "";
    const baseName = $("#base-name").val() || "";
    $("#base-dir").prop('disabled', true);
    $("#base-name").prop('disabled', true);
    $.ajax({
        url: '/run_script',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ base_dir: baseDir, base_name: baseName }),
        success: function(response) {
            if (response.status === 'success') {
                scriptRunning = true;
                $("#run-script-btn").prop('disabled', true);
                $("#terminate-script-btn").prop('disabled', false);
                $("#log-display").text("Script started...\n");
            } else {
                $("#log-display").text(`Error: ${response.message}\n`);
                $("#base-dir").prop('disabled', false);
                $("#base-name").prop('disabled', false);
            }
        },
        error: function(jqXHR, textStatus, errorThrown) {
            console.log("AJAX error:", textStatus, errorThrown);
            $("#log-display").text(`Error: Failed to start script\n`);
            $("#base-dir").prop('disabled', false);
            $("#base-name").prop('disabled', false);
        }
    });
}

function terminateScript() {
    $.ajax({
        url: '/terminate_script',
        type: 'POST',
        contentType: 'application/json',
        success: function(response) {
            console.log("Terminate script response:", response);
            if (response.status === 'success') {
                scriptRunning = false;
                $("#run-script-btn").prop('disabled', false);
                $("#terminate-script-btn").prop('disabled', true);
                $("#base-dir").prop('disabled', false);
                $("#base-name").prop('disabled', false);
                $("#log-display").append("Script terminated.\n");
            } else {
                $("#log-display").append(`Error: ${response.message}\n`);
                if (response.message.includes('No process running')) {
                    scriptRunning = false;
                    $("#run-script-btn").prop('disabled', false);
                    $("#terminate-script-btn").prop('disabled', true);
                    $("#base-dir").prop('disabled', false);
                    $("#base-name").prop('disabled', false);
                }
            }
        },
        error: function(jqXHR, textStatus, errorThrown) {
            console.log("AJAX error:", textStatus, errorThrown);
            $("#log-display").append(`Error: Failed to terminate script\n`);
            scriptRunning = false;
            $("#run-script-btn").prop('disabled', false);
            $("#terminate-script-btn").prop('disabled', true);
            $("#base-dir").prop('disabled', false);
            $("#base-name").prop('disabled', false);
        }
    });
}

function fetchLogs() {
    $.get('/get_logs', function(response) {
        if (response.status === 'success') {
            $("#log-display").text(response.logs);
        }
    }).fail(function(jqXHR, textStatus, errorThrown) {
        console.log("AJAX error:", textStatus, errorThrown);
        $("#log-display").append(`Error: Failed to fetch logs\n`);
    });
}

function clearLogs() {
    $.ajax({
        url: '/clear_logs',
        type: 'POST',
        contentType: 'application/json',
        success: function(response) {
            if (response.status === 'success') {
                $("#log-display").text("");
            } else {
                $("#log-display").append(`Error: Failed to clear logs - ${response.message}\n`);
            }
        },
        error: function(jqXHR, textStatus, errorThrown) {
            console.log("AJAX error:", textStatus, errorThrown);
            $("#log-display").append(`Error: Failed to clear logs - ${textStatus}\n`);
        }
    });
}