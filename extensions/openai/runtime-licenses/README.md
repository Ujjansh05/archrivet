# Bundled Python runtime notices

These notices supplement the runtime's original `LICENSE.txt`, which the plugin
builder preserves separately. The source installation identifies itself as
CPython 3.12.13, Windows x64, python-build-standalone build **20260602**.

| Component | Version and evidence | Included notice |
|---|---|---|
| OpenSSL | 3.5.6, observed using `ssl.OPENSSL_VERSION` and DLL version resources | `openssl.txt`, `openssl-copyright.txt` |
| libffi | 3.4.2, inferred from the exact Windows builder's pinned CPython source-deps commit | `libffi.txt` |
| XZ / liblzma | 5.8.1, inferred from the exact Windows builder and dependency pin | `xz.txt`, `xz-copying.txt` |
| SQLite | 3.53.1, observed using `sqlite3.sqlite_version` | `sqlite.txt` |
| Expat | 2.7.4, observed using `pyexpat.EXPAT_VERSION` | `expat.txt` |
| libmpdec | 2.5.1, observed using `decimal.__libmpdec_version__` | `mpdecimal.txt` |
| zlib | 1.3.1, observed using `zlib.ZLIB_RUNTIME_VERSION` | `zlib.txt` |

`provenance.txt` is machine-readable JSON containing the primary source URLs,
downloaded-text SHA-256 hashes, source/reference hashes, and hashes of the local
runtime binaries examined. Text is preserved verbatim. The OpenSSL copyright
section and libmpdec's complete opening license comment are extracted from the
recorded upstream files; their full source hashes and extraction descriptions
are retained.

The standalone project's general dependency table alone is insufficient to
identify Windows dependencies: its Windows build script uses a pinned libffi
source commit, and this CPython 3.12 build uses its vendored Expat and libmpdec.
The recorded observed versions take precedence over unrelated general pins.

The XZ notice applies to the linked liblzma library. No XZ command-line utilities,
GNU build tools, or associated scripts are added to the plugin by this work.
The runtime's existing `LICENSE.txt` also includes Microsoft runtime, bzip2,
Tcl/Tk, and Python notices; their preservation does not change their terms.

Remaining provenance limits: the local runtime was not independently matched
against an upstream release archive checksum, and libffi/liblzma versions were
not obtained from DLL version resources. No runtime archive was downloaded.
This is a supplemental notice inventory, not legal certification or a complete
source-to-binary audit. Changing the runtime requires repeating the inventory.
