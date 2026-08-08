import logging,logging.handlers,os,config

def setup(name):
    # Shared by brain.py and diagnostics.py so both land in the same rotating file (FR-1100-003)
    # — useful for correlating a diagnostic run against brain.py activity around the same time.
    log_dir=config.WILLY_LOG_ROOT  # §13 — was os.path.dirname(__file__)+config.LOG_DIR, now resolved once in storage.py
    os.makedirs(log_dir,exist_ok=True)
    root=logging.getLogger()
    if not root.handlers:
        # encoding='utf-8' explicit: this Pi's system locale is LANG=en_US (no .UTF-8 suffix),
        # so the default file encoding is strict iso8859-1 — any pre-existing log message with
        # a non-ASCII char (several use em-dashes/§) would raise UnicodeEncodeError on write and
        # silently drop that line instead of persisting it, defeating FR-1100-003 for exactly
        # the fault messages that matter most.
        file_handler=logging.handlers.RotatingFileHandler(
            os.path.join(log_dir,config.LOG_FILE),
            maxBytes=config.LOG_MAX_BYTES,backupCount=config.LOG_BACKUP_COUNT,encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)-7s %(name)s %(message)s',datefmt='%Y-%m-%d %H:%M:%S'))
        console_handler=logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)-7s %(message)s',datefmt='%H:%M:%S'))
        root.setLevel(logging.INFO)
        root.addHandler(file_handler); root.addHandler(console_handler)
    return logging.getLogger(name)
