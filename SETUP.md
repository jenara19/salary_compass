# 🧭 SalaryCompass — Setup Guide

Step-by-step instructions to get the app running on a new machine.
No prior Python experience needed.

---

## What you need

- A computer running **Windows, macOS, or Linux**
- **Python 3.10 or newer** (see Step 1 if you're not sure)
- The `salary-compass` folder (unzipped from the archive)
- An internet connection (one-time, to install dependencies)

---

## Step 1 — Check if Python is installed

Open a terminal:
- **Windows**: press `Win + R`, type `cmd`, press Enter
- **macOS**: press `Cmd + Space`, type `Terminal`, press Enter
- **Linux**: open your terminal app

Run:
```
python --version
```

You should see something like `Python 3.11.4`.

- If you get `Python 3.10.x` or higher → you're good, skip to Step 2.
- If you get `Python 3.9.x` or lower → install a newer version (see below).
- If you get `command not found` or an error → Python is not installed (see below).

### Installing Python (if needed)

**Windows:**
1. Go to https://www.python.org/downloads/
2. Click the big yellow "Download Python 3.x.x" button
3. Run the installer
4. ✅ **Important**: on the first screen, check **"Add Python to PATH"** before clicking Install
5. When done, close and reopen your terminal, then run `python --version` again

**macOS:**
1. Go to https://www.python.org/downloads/
2. Download and run the macOS installer
3. Or, if you have Homebrew: `brew install python`

**Linux (Ubuntu/Debian):**
```bash
sudo apt update && sudo apt install python3 python3-pip -y
```

---

## Step 2 — Navigate to the project folder

In your terminal, use `cd` to go into the unzipped `salary-compass` folder.

**Example — Windows:**
```
cd C:\Users\YourName\Downloads\salary-compass
```

**Example — macOS / Linux:**
```
cd ~/Downloads/salary-compass
```

To confirm you're in the right place, run:
```
dir        (Windows)
ls         (macOS / Linux)
```
You should see files like `app.py`, `requirements.txt`, `README.md`.

---

## Step 3 — (Recommended) Create a virtual environment

This keeps the app's dependencies isolated from your system Python.
Skip this step if you just want to get running quickly.

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

Your terminal prompt will change to show `(venv)` when the environment is active.
You'll need to run the `activate` command again each time you open a new terminal.

---

## Step 4 — Install dependencies

Run this once inside the project folder:

```bash
pip install -r requirements.txt
```

This downloads and installs: `streamlit`, `pandas`, `plotly`, `pyyaml`, `xlsxwriter`.

It may take 1–2 minutes. You'll see a lot of output — that's normal.
When it finishes you'll see `Successfully installed ...`.

If you get a `pip: command not found` error, try `pip3` instead:
```bash
pip3 install -r requirements.txt
```

---

## Step 5 — Start the app

```bash
python -m streamlit run app.py
```

After a few seconds you'll see:
```
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
```

The app will **open automatically in your browser**. If it doesn't, copy
`http://localhost:8501` and paste it into Chrome, Firefox, or Edge.

> ⚠️ Keep the terminal window open while using the app.
> Closing it stops the server.

---

## Step 6 — Stop the app

Go back to the terminal and press **Ctrl + C**.

---

## Troubleshooting

### "streamlit: command not found"
Use `python -m streamlit run app.py` instead of `streamlit run app.py`.

### "ModuleNotFoundError: No module named 'streamlit'"
Dependencies aren't installed. Go back to Step 4 and run `pip install -r requirements.txt`.

### "python: command not found" (macOS/Linux)
Try `python3` instead of `python`:
```bash
python3 -m streamlit run app.py
```

### Port 8501 already in use
Another instance is running. Either stop it (Ctrl+C in its terminal) or run on a different port:
```bash
python -m streamlit run app.py --server.port 8502
```
Then open `http://localhost:8502`.

### The app opens but shows an error / white screen
Make sure you ran the command from inside the `salary-compass` folder (Step 2).
The app needs the `data/`, `engine/`, and `output/` folders to be present.

### Numbers look wrong after editing a YAML file
Streamlit caches results. After editing any `.yaml` file in `data/`, you must
**restart the app** (Ctrl+C, then run the start command again) to see updated numbers.

---

## Updating the app

If you receive an updated version of `salary-compass`:
1. Stop the running app (Ctrl+C)
2. Replace the files with the new version
3. Run `pip install -r requirements.txt` again (in case dependencies changed)
4. Start the app again

---

## For developers

See `CONTEXT.md` for the full architecture reference, data schemas, tax engine details,
and known gotchas before making any code changes.
