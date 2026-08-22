====================================================
  HypeClip Studio - Portable Edition
====================================================

HOW TO RUN
  1. Move this whole folder anywhere you like
     (Desktop, D:\Tools, USB drive - anywhere).
  2. Double-click HypeClip.exe
     -> your browser opens the dashboard at http://127.0.0.1:8500
  3. A lightning icon appears in the system tray:
     right-click it for clipboard clipping, output folder, quit.

FIRST WINDOWS DEFENDER WARNING?
  Unsigned apps get a blue SmartScreen popup. Click "More info"
  -> "Run anyway". Normal for indie software without a certificate.

WHERE MY STUFF GOES
  Everything stays INSIDE this folder - nothing is installed:
    Data\output            finished clips (+ platform exports)
    Data\assets\sfx        sound effects (drop your own .mp3/.wav here)
    Data\assets\music      background music tracks
    Data\assets\watermarks logo PNGs
    Data\app               AI Patch Studio hot-fixes live here
    Data\backups           automatic backups of every applied patch
    Data\cache             whisper/AI model downloads
  Reset completely: delete the Data folder.
  Move the app: just move the folder - clips come along.

TROUBLESHOOTING
  Nothing happens?        Run HypeClip-Debug.exe to see the log.
  Port busy?              setx HYPECLIP_PORT 8600   then relaunch.
  Age-restricted streams: use cookies-from-browser chrome option.
  First transcription slow: model downloads once into Data\cache.

UPDATES
  Dashboard -> Software Updates:
    Online channel - paste a manifest URL to fetch official releases.
    AI channel     - copy any module prompt into ChatGPT/Claude/Gemini,
                     paste the rewritten file back, Apply and Restart.