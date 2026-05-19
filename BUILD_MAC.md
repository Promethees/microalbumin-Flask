# Building the macOS Installer DMG

This guide explains how to build the `EasyOKAPI.dmg` installer from the source files in `installer-mac/`.

## Prerequisites
- macOS (as it uses the native `hdiutil` command).
- The `installer-mac/` folder containing the `.command` and `.scpt` files.

## Build Instructions

1.  Open the **Terminal** app.
2.  Navigate to the repository root directory:
    ```bash
    cd /path/to/microalbumin-Flask
    ```
3.  Run the build script located in the `installer-mac` folder:
    ```bash
    ./installer-mac/build-dmg.sh
    ```
4.  The script will:
    - Cleanup previous builds.
    - Copy the contents of `installer-mac/` to a temporary directory.
    - Create a compressed DMG named `EasyOKAPI_1.0.8.dmg` in the project root.
    - Remove the temporary directory.

## Troubleshooting

- **Permissions**: If the script is not executable, run:
  ```bash
  chmod +x ./installer-mac/build-dmg.sh
  ```
- **File Missing**: Ensure that all `.command` and `.scpt` files are present in the `installer-mac/` directory before building.
