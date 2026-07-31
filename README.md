# Easy OKAPI Web application

## Setup and Usage
The web-based software is available at [https://www.easysensorkit.cbbiotec.vn/](https://www.easysensorkit.cbbiotec.vn/)

### Pages

| Path | Page | Template |
|---|---|---|
| `/` | Product landing page — what Easy OKAPI is, how to get it, how to cite it | `templates/landing.html` + `static/landing.css` |
| `/webapp` | The application itself (all four modes, files, charts, reports) | `templates/index.html` |

The landing page opens no session storage and does not refresh the account
idle-timeout stamp, so a visitor who never enters the app costs nothing.
Reviews and the citation block on it are read from the same curated files the
app uses (`testimonials.json`, `publications.json`).

### Run it locally 
	- Install `pyenv` with `Python 3.12.11` using `setup-install-pyenv.command`
	- Set local python version as `3.12.11` using `pyenv local 3.12.11`
	- Install dependencies using `pip3 install -r requirements.txt`
	- Install `gunicorn` with `pip3 install gunicorn`
	- Start the app locally with `gunicorn -k eventlet -w 1 main:app --bind 0.0.0.0:5000`
	- Open browser, access the software via address of `http://0.0.0.0:5000` or `http://localhost:5000`

### Online deployment (Heroku)
- **Log in to Heroku**: `heroku login`
- **Configure Buildpacks** (Only needed once):
  ```bash
  # Clear existing buildpacks
  heroku buildpacks:clear -a easysensor-kit
  # Add Node.js for automated obfuscation
  heroku buildpacks:add heroku/nodejs -a easysensor-kit
  # Add Python for the Flask app
  heroku buildpacks:add heroku/python -a easysensor-kit
  ```
- **Deploy**: 
  - Make changes and commit them: `git add . && git commit -m "Your message"`
  - Push the `online` branch to Heroku's `main`: `git push heroku online:main`
- **Notes**: 
  - The `heroku-postbuild` script in `package.json` will automatically run the obfuscation during every deployment.
  - You no longer need to run `npm run build` manually on your local machine.

### Environment Variables (Heroku)

Set these on Heroku with `heroku config:set VAR=value -a easysensor-kit`:

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Flask session encryption key |
| `DATABASE_URL` | Yes | PostgreSQL URL (auto-set by Heroku Postgres add-on) |
| `GOOGLE_ENCRYPTION_KEY` | Yes | Decrypts `credentials.enc` for Google Drive OAuth |
| `GOOGLE_REDIRECT_URI` | Yes | OAuth callback, e.g. `https://www.easysensorkit.cbbiotec.vn/auth/google/callback` |
| `GROQ_API_KEY` | Yes | Groq API key for the AI assistant |
| `SMTP_HOST` | Yes | SMTP server (default: `smtp.gmail.com`) |
| `SMTP_PORT` | No | SMTP port (default: `587`) |
| `SMTP_USER` | Yes | Sender email address |
| `SMTP_PASS` | Yes | SMTP app password |
| `APP_BASE_URL` | Yes | Public URL of the app, e.g. `https://www.easysensorkit.cbbiotec.vn` |
| `GITHUB_PAT` | Yes | GitHub Personal Access Token for proxying the source release |

### Account System (User Login & Registration)

The app includes a full account system backed by **Heroku Postgres** (`DATABASE_URL`). Users must create an account to download Easy OKAPI.

**User flows:**

| Flow | URL | Notes |
|---|---|---|
| Sign up | `/account/signup` | Requires name, email, password (≥ 8 chars). Sends a verification email. |
| Email verification | `/api/account/verify/<token>` | Link sent in the registration email; token expires in 24 hours. |
| Log in | `/account/login` | Email + password. Returns a 30-minute download token on success. |
| Forgot password | `/account/forgot-password` | Sends a reset link to the registered email. |
| Reset password | `/account/reset-password/<token>` | Token expires in 1 hour. |
| Delete account | (from account settings on main page) | Requires password confirmation; wipes all user data. |

**Key points:**
- Email must be verified before a user can log in and download.
- Sessions persist for **30 days** (`PERMANENT_SESSION_LIFETIME`).
- Passwords are hashed with **bcrypt** — never stored in plaintext.
- The download endpoint (`/api/download`) requires a valid JWT download token.

**Verify users in the database (Heroku Postgres):**
```bash
# List all registered users
heroku pg:psql --app easysensor-kit -c "SELECT * FROM users;"

# Check a specific user
heroku pg:psql --app easysensor-kit -c "SELECT id, email, name, is_verified, created_at, last_download FROM users WHERE email = 'user@example.com';"

# Manually verify a user (if the verification email was missed)
heroku pg:psql --app easysensor-kit -c "UPDATE users SET is_verified = TRUE WHERE email = 'user@example.com';"

# Count total registered users
heroku pg:psql --app easysensor-kit -c "SELECT COUNT(*) FROM users;"
```

> [!TIP]
> Run `heroku addons:info heroku-postgresql --app easysensor-kit` to check the database plan and connection status.

> [!NOTE]  
> **Offline Obfuscation**: If you still wish to obfuscate files locally (e.g., for testing or other platforms):
> 1. Ensure Node.js is installed.
> 2. Run `npm install` to get the build tools.
> 3. Run `npm run build` to generate the `.min` files in `static/dist/`.

### Update package.json with latest versions
	- Use `npm init -y && npm pkg set scripts.build="node build.js" scripts.start="gunicorn main:app" && npm install --save-dev javascript-obfuscator terser clean-css`

## Overview
Easy OKAPI (Open-colorimeter Kinetics Analysis Platform) is a cloud-hosted web application for colorimeter data analysis. It is developed by the Center for Bioscience and Biotechnology, HCMUS-VNU, and is inspired by the [IORodeo Open Colorimeter](https://iorodeo.com/products/open-colorimeter).

## Features

### File Management

Upload, edit, delete, copy, and merge `.csv` data files and `.json` calibration files directly in your browser session. Files are stored per-user and persist across sessions for registered users (backed by Firebase).

<div align="center">
	<img src="/images/blank.png" width="600">
	<!-- TODO: screenshot of file management panel -->
</div>

Supported data formats:
- [`Kinetics JSON`](https://github.com/Promethees/microalbumin-Flask/tree/online/json/exp_kinetics.json)
- [`Points JSON`](https://github.com/Promethees/microalbumin-Flask/tree/online/json/exp_point.json)
- [`Single Source CSV`](https://github.com/Promethees/microalbumin-Flask/tree/online/csv/single.csv)
- [`Multiple Source CSV`](https://github.com/Promethees/microalbumin-Flask/tree/online/csv/multi.csv)

### Measurement Modes

The application has **4 modes** selectable from the sidebar:

| Mode | Description |
|---|---|
| `kinetics` | Time-series absorbance data — computes max rate, slope, saturation, time to saturation |
| `point` | Single time-point endpoint assay |
| `calibrate` | Build a standard curve from known concentrations using selectable regression algorithms |
| `report` | Compile saved analysis snapshots into multi-file HTML or Excel reports |

<div align="center">
	<img src="/images/blank.png" width="600">
	<!-- TODO: screenshot of mode selector -->
</div>

### Data Display & Charts

Select a CSV file to visualize absorbance vs. time. Enable **Full Display** to overlay kinetics annotation lines (max rate window, linear progression, saturation) on the chart. Use **Display Range** to zoom into a time window and **Window Size** to control the sliding-window regression (kinetics mode only).

<div align="center">
	<img src="/images/blank.png" width="600">
	<!-- TODO: screenshot of data chart with annotations -->
</div>

Multi-source CSV files display each measurement channel in a separate chart. Use **Split by Sources** and **Filter by source count** to manage multi-source views. **Normalize** subtracts the baseline value from each source for direct comparison.

<div align="center">
	<img src="/images/blank.png" width="600">
	<!-- TODO: screenshot of multi-source display -->
</div>

### Kinetics Analysis

In `kinetics` mode, for each measurement source the app computes:
- **Max Rate** — highest ΔAbs/s found by sliding-window linear regression
- **Slope** — overall linear slope across the dataset
- **Sat** — plateau (saturation) absorbance value
- **Time To Sat** — time in minutes until the signal reaches the plateau

<div align="center">
	<img src="/images/blank.png" width="600">
	<!-- TODO: screenshot of kinetics analysis panel -->
</div>

### Calibration & Standard Curves

In `calibrate` mode, select which kinetics quantity (max rate, slope, sat, time to sat) or time point (point mode) to use as the X-axis, then fit a standard curve with one of:

- Linear · Polynomial · Logarithmic · Exponential · Michaelis-Menten

Set an R² threshold to filter poor-quality windows. Export the fitted coefficients as a `.json` file for later use.

<div align="center">
	<img src="/images/blank.png" width="600">
	<!-- TODO: screenshot of calibrate mode with regression curve -->
</div>

### Concentration Derivation

Load a saved standard-curve JSON to automatically convert measured values into analyte concentrations. The derived concentration is shown alongside each source's analysis panel.

<div align="center">
	<img src="/images/blank.png" width="600">
	<!-- TODO: screenshot of derived concentration display -->
</div>

### Export

- **Export Analysis** — save kinetics/point results to a new CSV file
- **Export Coefficients** — save the fitted standard-curve coefficients to a JSON file
- **Export to Report** — push the current analysis snapshot into a named report subject

<div align="center">
	<img src="/images/blank.png" width="600">
	<!-- TODO: screenshot of export panel -->
</div>

### Report System

Switch to `report` mode to manage saved analysis snapshots organized into **subjects**. Reorder, rename, copy, merge, or delete subjects and items. Generate a final output as:
- **HTML report** — printable in-browser, saveable as PDF
- **Excel workbook** — formatted sheets with embedded charts per subject

<div align="center">
	<img src="/images/blank.png" width="600">
	<!-- TODO: screenshot of report console -->
</div>

### Google Drive Integration

Connect your Google account to sync all session files (CSV + JSON) to a Drive folder of your choice. Data can be pushed to Drive or pulled back into the session at any time. Optional auto-sync on page close.

<div align="center">
	<img src="/images/blank.png" width="600">
	<!-- TODO: screenshot of Drive panel -->
</div>

### AI Assistant (OKAPI Assistant)

A floating chat widget powered by [Groq](https://groq.com). Ask questions about your data, calibration coefficients, or app navigation. The assistant responds with text explanations or launches an interactive step-by-step spotlight guide directly in the UI.

Supported languages: English, Tiếng Việt, 中文 (简体), Français, 日本語, Русский.

<div align="center">
	<img src="/images/blank.png" width="600">
	<!-- TODO: screenshot of AI chat widget -->
</div>

## License
* This project is for educational purposes and does not include a specific license. Feel free to use and modify it as needed.
