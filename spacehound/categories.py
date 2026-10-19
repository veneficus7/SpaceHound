"""File type categories used for statistics and colouring."""

# (key, label, colour) - order matters, the index is stored in results.
CATEGORIES = [
    ("video", "Video", "#e0603c"),
    ("image", "Images", "#f0a93c"),
    ("audio", "Audio", "#c27fb5"),
    ("document", "Documents", "#7fb8c9"),
    ("archive", "Archives", "#b8834f"),
    ("diskimage", "Disk images & VMs", "#d9758f"),
    ("code", "Code & dev", "#6cb58a"),
    ("app", "Apps & installers", "#8c9edb"),
    ("system", "System & libraries", "#8a7d6b"),
    ("data", "Databases & data", "#4fa89a"),
    ("game", "Game & 3D assets", "#b5c25b"),
    ("cache", "Caches & temp", "#d8c3a0"),
    ("other", "Other", "#6e6252"),
]

CATEGORY_KEYS = [c[0] for c in CATEGORIES]
OTHER = len(CATEGORIES) - 1

_EXTS = {
    "cache": "aecache cache tmp temp nvph cfa pek pfl cl_cache ocl mcdb ims body file dxcache shadercache cachefile tmp2 crdownload partial part download",
    "video": "mp4 m4v mkv avi mov wmv flv webm mpg mpeg m2ts mts ts vob 3gp 3g2 ogv rm rmvb asf divx f4v braw r3d mxf dv prproj drp aep aet mogrt veg",
    "image": "jpg jpeg png gif bmp tif tiff webp heic heif raw cr2 cr3 nef arw orf rw2 dng psd psb svg ico avif jxl xcf kra ai eps exr hdr tga dds",
    "audio": "mp3 wav flac aac ogg oga opus m4a wma aiff aif alac ape mid midi amr ac3 dts mka caf",
    "document": "pdf doc docx odt rtf txt md xls xlsx xlsm ods csv ppt pptx odp pages numbers key epub mobi azw azw3 djvu tex one onepkg xps oxps vsd vsdx pub msg eml",
    "archive": "zip rar 7z tar gz tgz bz2 tbz2 xz txz lz lzma zst cab arj z lz4 apkm xapk",
    "diskimage": "iso img vhd vhdx vmdk vdi qcow qcow2 hdd ova ovf wim esd swm dmg avhd avhdx vmem vmsn vmss sav",
    "code": "py pyc pyd pyi ipynb js mjs cjs ts tsx jsx java kt kts class jar aar dex c h cpp cc hpp cs go rs rb php swift m mm scala lua r dart vue svelte html htm css scss sass less json xml yaml yml toml ini cfg gradle lock map wasm sh ps1 bat cmd sln csproj vcxproj pdb ilk obj o a lib so dylib iml idx pack rlib rmeta bin2 apk aab node nupkg",
    "app": "exe msi msix msixbundle appx appxbundle msp msu com scr appimage deb rpm pkg asar",
    "system": "dll sys drv ocx cpl mui cat manifest etl evtx log dmp mdmp hiberfil bak old blf regtrans-ms dat db-wal db-shm etl2 nls ttf otf woff woff2 fon",
    "data": "db sqlite sqlite3 mdb accdb sql dbf parquet feather h5 hdf5 npy npz pkl pickle pt pth ckpt safetensors onnx tflite gguf ggml bin model weights tfrecord arrow avro orc mdf ldf ndf bak2 ost pst nsf edb ldb jsonl wal",
    "game": "pak vpk bsa ba2 upk uasset umap bundle assets resource forge big wad pk3 pk4 gcf ncf vpp rpf mpq unity3d fbx obj3d blend max ma mb 3ds dae gltf glb stl usd usdz levelstream levelrender bik bk2 xwb xnb",
}

EXT_TO_CAT = {}
for _key, _exts in _EXTS.items():
    _idx = CATEGORY_KEYS.index(_key)
    for _e in _exts.split():
        EXT_TO_CAT.setdefault(_e, _idx)


def ext_of(name):
    """Lower-case extension without the dot ('' when there is none)."""
    dot = name.rfind(".")
    if dot <= 0 or dot == len(name) - 1:
        return ""
    ext = name[dot + 1:].lower()
    return ext if len(ext) <= 12 else ""


def cat_of_ext(ext):
    return EXT_TO_CAT.get(ext, OTHER)


def cat_of(name):
    return EXT_TO_CAT.get(ext_of(name), OTHER)


def category_table():
    return [{"key": k, "label": l, "color": c} for k, l, c in CATEGORIES]
