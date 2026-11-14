# SPDX-License-Identifier: GPL-3.0-or-later
"""Textos de la interfaz en español e inglés (sin dependencias ni archivos externos)."""

from __future__ import annotations

import locale
import os

LANGS = ("es", "en")

# clave: (español, inglés)
_T: dict[str, tuple[str, str]] = {
    # Pestañas y cabecera
    "tab_playlists": ("Playlists", "Playlists"),
    "tab_spotify": ("Spotify", "Spotify"),
    "tab_settings": ("Ajustes", "Settings"),
    "lang_tip": ("Idioma: español. Clic para cambiar a inglés", "Language: English. Click to switch to Spanish"),
    # Barra de playlists
    "add": ("Agregar TXT", "Add TXT"),
    "add_tip": ("Agregar listas .txt, una playlist por archivo (Ctrl+O)", "Add .txt lists, one playlist per file (Ctrl+O)"),
    "remove": ("Quitar", "Remove"),
    "remove_tip": ("Quitar de la lista las playlists seleccionadas (Supr)", "Remove the selected playlists from the list (Del)"),
    "clear": ("Vaciar", "Clear"),
    "clear_tip": ("Vaciar la lista (no borra archivos)", "Clear the list (no files are deleted)"),
    "parallel": ("En paralelo", "Parallel"),
    "parallel_tip": ("Cantidad de canciones que se descargan a la vez", "How many songs are downloaded at the same time"),
    "dest_tip": ("Carpeta de destino: {dest}\nCada playlist se guarda en una subcarpeta con su nombre. Clic para cambiarla.",
                 "Destination folder: {dest}\nEach playlist is saved in a subfolder with its name. Click to change it."),
    "dest_pick": ("Elegir la carpeta de destino", "Choose the destination folder"),
    "open_folder": ("Abrir", "Open"),
    "open_folder_tip": ("Abrir {dest}", "Open {dest}"),
    "download": ("Descargar", "Download"),
    "download_tip": ("Descargar todo lo pendiente (Ctrl+D)", "Download everything pending (Ctrl+D)"),
    "stop": ("Detener", "Stop"),
    "stop_tip": ("Detener las descargas en curso", "Stop the running downloads"),
    # Lista
    "col_name": ("Playlist / canción", "Playlist / song"),
    "col_result": ("Resultado", "Result"),
    "col_status": ("Estado", "Status"),
    "songs": ("{n} canciones", "{n} songs"),
    "songs_one": ("1 canción", "1 song"),
    "progress_of": ("{done} de {n}", "{done} of {n}"),
    "st_pending": ("Pendiente", "Pending"),
    "st_queued": ("En cola", "Queued"),
    "st_resolving": ("Buscando…", "Searching…"),
    "st_downloading": ("Descargando {pct} %", "Downloading {pct}%"),
    "st_ok": ("Descargada", "Downloaded"),
    "st_copied": ("Copiada de otra playlist", "Copied from another playlist"),
    "st_skipped": ("Ya estaba", "Already there"),
    "st_failed": ("Falló", "Failed"),
    "st_cancelled": ("Cancelada", "Cancelled"),
    "pl_empty": ("Sin canciones", "No songs"),
    "pl_running": ("Descargando…", "Downloading…"),
    "pl_done": ("Completa", "Complete"),
    "pl_done_failed": ("{bad} fallidas", "{bad} failed"),
    "pl_done_failed_one": ("1 fallida", "1 failed"),
    "pl_tip": ("{folder}\nDoble clic para abrir la carpeta", "{folder}\nDouble-click to open the folder"),
    "videos": ("{n} videos", "{n} videos"),
    # Estado vacío
    "empty_title": ("Arrastrá tus listas .txt acá", "Drop your .txt lists here"),
    "empty_sub": ("Cada archivo es una playlist: una canción por línea, como «Canción - Artista» o una URL.\n"
                  "También podés usar Agregar TXT o traerlas desde la pestaña Spotify.",
                  "Each file is a playlist: one song per line, like “Song - Artist” or a URL.\n"
                  "You can also use Add TXT or bring them in from the Spotify tab."),
    "pick_title": ("Agregar listas de canciones", "Add song lists"),
    "pick_filter": ("Listas de texto (*.txt);;Todos los archivos (*)", "Text lists (*.txt);;All files (*)"),
    # Consola
    "console": ("Consola", "Console"),
    "console_copy": ("Copiar todo", "Copy all"),
    "console_clear": ("Limpiar", "Clear"),
    "status_ready": ("Listo", "Ready"),
    "status_downloading": ("Descargando · {done} de {n}", "Downloading · {done} of {n}"),
    "status_downloading_bad": ("Descargando · {done} de {n} · {bad} fallidas", "Downloading · {done} of {n} · {bad} failed"),
    "status_stopping": ("Deteniendo…", "Stopping…"),
    "status_exporting": ("Exportando de Spotify…", "Exporting from Spotify…"),
    "status_updating": ("Actualizando yt-dlp…", "Updating yt-dlp…"),
    # Mensajes de consola: generales
    "log_welcome": ("music-dlp {version}", "music-dlp {version}"),
    "log_ytdlp": ("yt-dlp {version} ({origin})", "yt-dlp {version} ({origin})"),
    "origin_bundled": ("incluido", "bundled"),
    "origin_user": ("actualizado por vos", "updated by you"),
    "log_ffmpeg": ("ffmpeg: {path}", "ffmpeg: {path}"),
    "log_no_ffmpeg": ("No se encontró ffmpeg: sin él no se pueden convertir las canciones. Instalalo con el gestor de paquetes de tu sistema.",
                      "ffmpeg was not found: songs cannot be converted without it. Install it with your system's package manager."),
    "log_no_deno": ("Aviso: no se encontró deno. YouTube puede ofrecer menos formatos; instalar deno lo mejora.",
                    "Note: deno was not found. YouTube may offer fewer formats; installing deno improves this."),
    "log_added": ("Agregada «{name}»: {songs}", "Added “{name}”: {songs}"),
    "log_skipped_files": ("Archivos ignorados (repetidos, vacíos o no son listas de texto): {n}", "Files ignored (duplicates, empty or not text lists): {n}"),
    "log_dest": ("Carpeta de destino: {dest}", "Destination folder: {dest}"),
    "log_txt_dir": ("Carpeta de los TXT de Spotify: {dest}", "Spotify TXT folder: {dest}"),
    # Mensajes de consola: descargas
    "log_dl_start": ("Descargando {songs} en {dest} ({p} en paralelo, {fmt})", "Downloading {songs} into {dest} ({p} in parallel, {fmt})"),
    "log_dl_nothing": ("No hay nada pendiente para descargar.", "There is nothing pending to download."),
    "log_song_ok": ("✔ [{pl}] {line}  →  {title}", "✔ [{pl}] {line}  →  {title}"),
    "log_song_copied": ("✔ [{pl}] {line}  (copiada de otra playlist)", "✔ [{pl}] {line}  (copied from another playlist)"),
    "log_song_skipped": ("• [{pl}] {line}  (ya estaba)", "• [{pl}] {line}  (already there)"),
    "log_song_failed": ("✘ [{pl}] {line}  ({error})", "✘ [{pl}] {line}  ({error})"),
    "log_pl_done": ("Playlist «{pl}» · descargadas: {ok} · ya estaban: {skipped} · fallidas: {bad}", "Playlist “{pl}” · downloaded: {ok} · already there: {skipped} · failed: {bad}"),
    "log_failed_file": ("Las fallidas de «{pl}» quedaron en {path}", "The failed songs of “{pl}” were saved to {path}"),
    "log_dl_done": ("Terminado · descargadas: {ok} · ya estaban: {skipped} · fallidas: {bad}", "Finished · downloaded: {ok} · already there: {skipped} · failed: {bad}"),
    "log_dl_cancelled": ("Descargas detenidas · descargadas: {ok} · fallidas: {bad} · sin terminar: {left}", "Downloads stopped · downloaded: {ok} · failed: {bad} · unfinished: {left}"),
    "log_stopping": ("Deteniendo: se cortan las descargas en curso…", "Stopping: the running downloads are being cut…"),
    "log_dl_error": ("Las descargas se interrumpieron por un error: {error}", "The downloads were interrupted by an error: {error}"),
    "err_no_results": ("sin resultados", "no results"),
    "err_no_ffmpeg": ("falta ffmpeg", "ffmpeg is missing"),
    "unknown_artist": ("Desconocido", "Unknown"),
    "failed_name": ("fallidas.txt", "failed.txt"),
    # Spotify: formulario
    "sp_title": ("Exportar tus playlists de Spotify", "Export your Spotify playlists"),
    "sp_intro": ("Necesitás una app propia en el <a href='https://developer.spotify.com/dashboard'>Spotify Developer Dashboard</a> "
                 "con <b>Web API</b> marcada y esta Redirect URI:",
                 "You need your own app in the <a href='https://developer.spotify.com/dashboard'>Spotify Developer Dashboard</a> "
                 "with <b>Web API</b> ticked and this Redirect URI:"),
    "sp_copy_uri": ("Copiar la Redirect URI", "Copy the Redirect URI"),
    "sp_uri_copied": ("Redirect URI copiada al portapapeles.", "Redirect URI copied to the clipboard."),
    "sp_client_id": ("Client ID", "Client ID"),
    "sp_client_secret": ("Client Secret", "Client Secret"),
    "show": ("Mostrar", "Show"),
    "hide": ("Ocultar", "Hide"),
    "sp_own_only": ("Solo las playlists que creé yo", "Only the playlists I created"),
    "sp_liked": ("Incluir «Canciones que te gustan»", "Include “Liked Songs”"),
    "sp_export": ("Exportar playlists", "Export playlists"),
    "sp_export_tip": ("Abre el navegador para autorizar (solo la primera vez) y guarda un TXT por playlist",
                      "Opens the browser to authorize (first time only) and saves one TXT per playlist"),
    "sp_cancel": ("Cancelar", "Cancel"),
    "sp_store_keyring": ("Las credenciales se guardan en el llavero del sistema.", "The credentials are saved in the system keyring."),
    "sp_store_file": ("Las credenciales se guardan en un archivo privado (permisos 600).", "The credentials are saved in a private file (mode 600)."),
    "sp_store_memory": ("Las credenciales no se guardan: se olvidan al cerrar la app.", "The credentials are not saved: they are forgotten when the app closes."),
    "sp_store_change": ("Se cambia en Ajustes → Seguridad.", "Change it in Settings → Security."),
    "liked_name": ("Canciones que te gustan", "Liked Songs"),
    # Spotify: resultados
    "sp_results": ("Playlists exportadas", "Exported playlists"),
    "sp_results_empty": ("Cuando termine la exportación, tus playlists aparecen acá para importarlas a la lista de descargas.",
                         "When the export finishes, your playlists show up here so you can import them into the download list."),
    "sp_col_name": ("Playlist", "Playlist"),
    "sp_col_songs": ("Canciones", "Songs"),
    "sp_all": ("Todas", "All"),
    "sp_none": ("Ninguna", "None"),
    "sp_open_txt": ("Abrir carpeta", "Open folder"),
    "sp_import": ("Importar a descargas", "Import to downloads"),
    "sp_import_n": ("Importar {n} a descargas", "Import {n} to downloads"),
    "sp_import_tip": ("Agrega las playlists marcadas a la pestaña Playlists", "Adds the ticked playlists to the Playlists tab"),
    # Spotify: consola
    "log_sp_need": ("Completá el Client ID y el Client Secret.", "Fill in the Client ID and the Client Secret."),
    "log_sp_login": ("Abriendo el navegador: aceptá el pedido de Spotify para seguir (esperando hasta 5 minutos)…",
                     "Opening the browser: accept the Spotify request to continue (waiting up to 5 minutes)…"),
    "log_sp_url": ("Si no se abrió, entrá a: {url}", "If it did not open, go to: {url}"),
    "log_sp_session": ("Sesión de Spotify guardada: no hace falta volver a autorizar.", "Spotify session saved: no need to authorize again."),
    "log_sp_found": ("Playlists encontradas en Spotify: {n}. Exportando a {dest}", "Playlists found on Spotify: {n}. Exporting to {dest}"),
    "log_sp_ok": ("✔ {name}  ({songs}) → {file}", "✔ {name}  ({songs}) → {file}"),
    "log_sp_failed": ("✘ {name}: Spotify no deja leerla (error {status})", "✘ {name}: Spotify does not allow reading it (error {status})"),
    "log_sp_done": ("Exportación terminada. Playlists exportadas: {n}. Elegí cuáles importar en la pestaña Spotify.", "Export finished. Playlists exported: {n}. Choose which to import in the Spotify tab."),
    "log_sp_imported": ("Playlists importadas a la lista de descargas: {n}", "Playlists imported into the download list: {n}"),
    "sp_err_cancelled": ("Exportación cancelada.", "Export cancelled."),
    "sp_err_network": ("No se pudo conectar con Spotify: {detail}", "Could not connect to Spotify: {detail}"),
    "sp_err_bad_credentials": ("Spotify rechazó el Client ID o el Client Secret. Revisalos.", "Spotify rejected the Client ID or the Client Secret. Check them."),
    "sp_err_auth_failed": ("Spotify no completó la autorización (error {status}). {detail}", "Spotify did not complete the authorization (error {status}). {detail}"),
    "sp_err_session_expired": ("La sesión de Spotify venció. Volvé a exportar para autorizar de nuevo.", "The Spotify session expired. Export again to re-authorize."),
    "sp_err_auth_denied": ("No autorizaste el acceso en Spotify.", "You did not grant access in Spotify."),
    "sp_err_auth_timeout": ("Se acabó el tiempo de espera de la autorización.", "The authorization timed out."),
    "sp_err_port_busy": ("El puerto {detail} está ocupado por otro programa; cerralo y probá de nuevo.", "Port {detail} is in use by another program; close it and try again."),
    "sp_err_forbidden": ("Spotify negó el acceso (403). Si la app está en modo desarrollo, agregá tu cuenta en User Management.",
                         "Spotify denied access (403). If the app is in development mode, add your account in User Management."),
    "sp_err_api": ("Spotify respondió con un error ({status}).", "Spotify answered with an error ({status})."),
    "sp_err_other": ("Error inesperado: {detail}", "Unexpected error: {detail}"),
    # Ajustes: descargas
    "set_downloads": ("Descargas", "Downloads"),
    "set_format": ("Formato de audio", "Audio format"),
    "fmt_mp3": ("MP3 (compatible con todo)", "MP3 (plays everywhere)"),
    "fmt_opus": ("Opus (audio original de YouTube, sin reconvertir)", "Opus (YouTube's original audio, no re-encoding)"),
    "fmt_m4a": ("M4A / AAC", "M4A / AAC"),
    "fmt_flac": ("FLAC (archivos grandes, sin mejora real)", "FLAC (large files, no real gain)"),
    "opt_metadata": ("Metadatos (título, artista, álbum)", "Metadata (title, artist, album)"),
    "opt_cover": ("Carátula incrustada", "Embedded cover art"),
    "opt_skip": ("Saltar las ya descargadas", "Skip already downloaded songs"),
    "opt_skip_tip": ("No vuelve a bajar lo que ya está en la carpeta, y copia las canciones que ya bajaste en otra playlist",
                     "Does not download again what is already in the folder, and copies songs you already downloaded in another playlist"),
    "opt_failed": ("Archivo de fallidas en cada playlist", "Failed-songs file in each playlist"),
    "opt_failed_tip": ("Guarda en la carpeta de la playlist un TXT con las canciones que fallaron, listo para volver a arrastrar",
                       "Saves a TXT with the songs that failed in the playlist folder, ready to be dropped again"),
    "opt_ytmusic": ("Buscar en YouTube Music", "Search on YouTube Music"),
    "opt_ytmusic_tip": ("Suele encontrar el audio oficial en vez de videoclips; si no hay resultados busca en YouTube",
                        "Usually finds the official audio instead of music videos; falls back to YouTube when there are no results"),
    "opt_artist": ("Subcarpetas por artista", "Subfolders per artist"),
    "opt_artist_tip": ("Apagado: todas las canciones van sueltas dentro de la carpeta de la playlist",
                       "Off: every song goes straight into the playlist folder"),
    "opt_numbers": ("Numerar según el orden de la playlist", "Number files in playlist order"),
    "opt_numbers_tip": ("Antepone 01, 02… al nombre del archivo", "Prefixes the file name with 01, 02…"),
    "opt_sponsor": ("Recortar partes sin música (SponsorBlock)", "Cut non-music parts (SponsorBlock)"),
    "opt_sponsor_tip": ("Quita intros y partes habladas de los videoclips. Consulta el servicio externo sponsor.ajay.app",
                        "Removes intros and talking from music videos. Queries the external service sponsor.ajay.app"),
    "set_txt_dir": ("Carpeta de los TXT de Spotify", "Spotify TXT folder"),
    "txt_pick": ("Elegir la carpeta de los TXT de Spotify", "Choose the Spotify TXT folder"),
    # Ajustes: seguridad
    "set_security": ("Seguridad", "Security"),
    "sec_intro": ("Dónde se guardan el Client ID, el Client Secret y la sesión de Spotify:",
                  "Where the Client ID, the Client Secret and the Spotify session are kept:"),
    "sec_keyring": ("Llavero del sistema (recomendado)", "System keyring (recommended)"),
    "sec_keyring_sub": ("Cifrado por KWallet, GNOME Keyring u otro llavero.", "Encrypted by KWallet, GNOME Keyring or another keyring."),
    "sec_file": ("Archivo privado", "Private file"),
    "sec_file_sub": ("Texto plano en {path}, legible solo por tu usuario.", "Plain text in {path}, readable only by your user."),
    "sec_memory": ("Solo en memoria", "Memory only"),
    "sec_memory_sub": ("Nada toca el disco; hay que ingresarlas y autorizar en cada sesión.", "Nothing touches the disk; you enter them and authorize every session."),
    "sec_forget": ("Olvidar credenciales y sesión", "Forget credentials and session"),
    "sec_forget_tip": ("Borra el Client ID, el Client Secret y la sesión de Spotify de todos los almacenes",
                       "Deletes the Client ID, the Client Secret and the Spotify session from every store"),
    "log_forgotten": ("Credenciales y sesión de Spotify borradas.", "Spotify credentials and session deleted."),
    "log_mode": ("Las credenciales ahora se guardan en: {mode}", "The credentials are now kept in: {mode}"),
    "log_vault_error": ("No se pudo usar el llavero del sistema ({detail}). Por ahora las credenciales quedan solo en memoria.",
                        "The system keyring could not be used ({detail}). For now the credentials are kept in memory only."),
    "log_vault_save_error": ("No se pudieron guardar las credenciales: {detail}", "The credentials could not be saved: {detail}"),
    # Ajustes: yt-dlp y acerca de
    "set_ytdlp": ("yt-dlp", "yt-dlp"),
    "yt_version": ("Versión en uso: {version} ({origin})", "Version in use: {version} ({origin})"),
    "yt_loading": ("Versión en uso: …", "Version in use: …"),
    "yt_note": ("YouTube cambia seguido. Si las descargas empiezan a fallar, actualizá yt-dlp: se baja de PyPI y se verifica su suma SHA-256.",
                "YouTube changes often. If downloads start failing, update yt-dlp: it is fetched from PyPI and its SHA-256 checksum is verified."),
    "yt_update": ("Actualizar yt-dlp", "Update yt-dlp"),
    "log_yt_check": ("Buscando la última versión de yt-dlp en PyPI…", "Looking for the latest yt-dlp version on PyPI…"),
    "log_yt_versions": ("yt-dlp en uso: {current} · última: {latest}", "yt-dlp in use: {current} · latest: {latest}"),
    "log_yt_downloading": ("Bajando {file}…", "Fetching {file}…"),
    "log_yt_updated": ("yt-dlp actualizado a {version}.", "yt-dlp updated to {version}."),
    "log_yt_latest": ("yt-dlp ya está en la última versión ({version}).", "yt-dlp is already at the latest version ({version})."),
    "log_yt_busy": ("Esperá a que terminen las descargas para actualizar yt-dlp.", "Wait for the downloads to finish before updating yt-dlp."),
    "up_err_network": ("No se pudo conectar con PyPI: {detail}", "Could not connect to PyPI: {detail}"),
    "up_err_checksum": ("La suma SHA-256 del archivo no coincide; no se instaló nada.", "The file's SHA-256 checksum does not match; nothing was installed."),
    "up_err_invalid": ("La respuesta de PyPI no es la esperada: {detail}", "PyPI's answer is not what was expected: {detail}"),
    "set_about": ("Acerca de", "About"),
    "about_text": ("music-dlp {version} · GPL-3.0-or-later<br>Sin telemetría. Solo se conecta a YouTube, a Spotify cuando exportás y a PyPI cuando actualizás yt-dlp."
                   "<br><a href='https://github.com/mrsalvaa/music-dlp'>github.com/mrsalvaa/music-dlp</a>",
                   "music-dlp {version} · GPL-3.0-or-later<br>No telemetry. It only connects to YouTube, to Spotify when you export and to PyPI when you update yt-dlp."
                   "<br><a href='https://github.com/mrsalvaa/music-dlp'>github.com/mrsalvaa/music-dlp</a>"),
}

_lang = "en"


def system_language() -> str:
    for var in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
        value = os.environ.get(var, "")
        if value:
            return "es" if value.lower().startswith("es") else "en"
    try:
        code = locale.getlocale()[0] or ""
    except ValueError:
        code = ""
    return "es" if code.lower().startswith("es") else "en"


def set_language(lang: str) -> None:
    global _lang
    _lang = lang if lang in LANGS else "en"


def language() -> str:
    return _lang


def has(key: str) -> bool:
    return key in _T


def tr(key: str, **kwargs) -> str:
    text = _T[key][LANGS.index(_lang)]
    return text.format(**kwargs) if kwargs else text


def songs(n: int) -> str:
    return tr("songs_one") if n == 1 else tr("songs", n=n)
