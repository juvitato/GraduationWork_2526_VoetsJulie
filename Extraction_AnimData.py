import maya.cmds as cmds
import csv
import os

# ==========================================================
# Globals
# ==========================================================
WINDOW = "UVTextureExportUI"
EXPORT_PATH = ""
TEXTURE_CHECKBOXES = {}

# ==========================================================
# Scene Queries
# ==========================================================
def get_materials_from_geo(geo):
    materials = set()
    shapes = cmds.listRelatives(geo, shapes=True, fullPath=True) or []
    for s in shapes:
        sgs = cmds.listConnections(s + ".instObjGroups[0]", type="shadingEngine") or []
        for sg in sgs:
            mats = cmds.listConnections(sg + ".surfaceShader", s=True, d=False) or []
            materials.update(mats)
    return list(materials)

def get_file_textures_from_material(material):
    """Find ALL file nodes contributing to this material"""
    files = set()
    history = cmds.listHistory(material, pruneDagObjects=True) or []
    for h in history:
        if cmds.nodeType(h) == "file":
            files.add(h)
    return sorted(files)

def get_place2d(file_node):
    p = cmds.listConnections(file_node + ".uvCoord", s=True, d=False)
    return p[0] if p else None

def get_active_image(file_node):
    if cmds.objExists(file_node + ".useFrameExtension"):
        if cmds.getAttr(file_node + ".useFrameExtension"):
            return cmds.getAttr(file_node + ".frameExtension")
    return None

# ==========================================================
# UI Texture Collection
# ==========================================================
def refresh_texture_list():
    global TEXTURE_CHECKBOXES
    TEXTURE_CHECKBOXES.clear()

    if cmds.columnLayout("textureColumn", exists=True):
        cmds.deleteUI("textureColumn")

    cmds.setParent("textureScroll")
    cmds.columnLayout("textureColumn", adjustableColumn=True)

    sel = cmds.ls(sl=True)
    if not sel:
        cmds.text(label="No geometry selected.")
        return

    geo = sel[0]
    materials = get_materials_from_geo(geo)

    textures = set()
    for mat in materials:
        textures.update(get_file_textures_from_material(mat))

    if not textures:
        cmds.text(label="No file textures found.")
        return

    for tex in sorted(textures):
        cb = cmds.checkBox(label=tex, v=True)
        TEXTURE_CHECKBOXES[tex] = cb

# ==========================================================
# Export Logic
# ==========================================================
def export_textures(options, meta, collect_all):
    global EXPORT_PATH

    if not EXPORT_PATH:
        cmds.warning("Choose an export path.")
        return

    sel = cmds.ls(sl=True)
    if not sel:
        cmds.warning("Select geometry.")
        return

    geo = sel[0]
    materials = get_materials_from_geo(geo)

    start = int(cmds.playbackOptions(q=True, min=True))
    end   = int(cmds.playbackOptions(q=True, max=True))

    base_dir = os.path.dirname(EXPORT_PATH)
    base_name = os.path.splitext(os.path.basename(EXPORT_PATH))[0]

    for mat in materials:
        for file_node in get_file_textures_from_material(mat):

            if file_node not in TEXTURE_CHECKBOXES:
                continue
            if not cmds.checkBox(TEXTURE_CHECKBOXES[file_node], q=True, v=True):
                continue

            place = get_place2d(file_node)
            if not place:
                continue

            csv_path = os.path.join(
                base_dir,
                f"{base_name}_{file_node}.csv"
            )

            header = ["Frame"]
            if meta["geo"]:
                header.append("Geometry")
            if meta["mat"]:
                header.append("Material")
            if meta["file"]:
                header.append("FileTexture")

            header.extend(options)
            rows = []
            last_state = None

            for f in range(start, end + 1):
                cmds.currentTime(f, edit=True)

                state = []
                data = []

                if "ActiveImage" in options:
                    v = get_active_image(file_node)
                    state.append(v)
                    data.append(v)

                if "OffsetU" in options:
                    v = cmds.getAttr(place + ".offsetU")
                    state.append(v)
                    data.append(v)

                if "OffsetV" in options:
                    v = cmds.getAttr(place + ".offsetV")
                    state.append(v)
                    data.append(v)

                if "ScaleU" in options:
                    v = cmds.getAttr(place + ".repeatU")
                    state.append(v)
                    data.append(v)

                if "ScaleV" in options:
                    v = cmds.getAttr(place + ".repeatV")
                    state.append(v)
                    data.append(v)

                if "RotateUV" in options:
                    v = cmds.getAttr(place + ".rotateUV")
                    state.append(v)
                    data.append(v)

                if collect_all or state != last_state:
                    row = [f]
                    if meta["geo"]:
                        row.append(geo)
                    if meta["mat"]:
                        row.append(mat)
                    if meta["file"]:
                        row.append(file_node)
                    row.extend(data)
                    rows.append(row)
                    last_state = state

            if rows:
                with open(csv_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(header)
                    writer.writerows(rows)

    cmds.inViewMessage(
        amg="<hl>Texture export complete</hl>",
        pos="midCenter",
        fade=True
    )

# ==========================================================
# UI Callbacks
# ==========================================================
def browse_path():
    global EXPORT_PATH
    p = cmds.fileDialog2(fileMode=0, fileFilter="CSV (*.csv)")
    if p:
        EXPORT_PATH = p[0]
        cmds.textField("pathField", e=True, text=EXPORT_PATH)

def run_export():
    options = []
    for key, cb in [
        ("ActiveImage", "cb_img"),
        ("OffsetU", "cb_ou"),
        ("OffsetV", "cb_ov"),
        ("ScaleU", "cb_su"),
        ("ScaleV", "cb_sv"),
        ("RotateUV", "cb_r")
    ]:
        if cmds.checkBox(cb, q=True, v=True):
            options.append(key)

    if not options:
        cmds.warning("Select values to export.")
        return

    meta = {
        "geo":  cmds.checkBox("cb_geo",  q=True, v=True),
        "mat":  cmds.checkBox("cb_mat",  q=True, v=True),
        "file": cmds.checkBox("cb_file", q=True, v=True)
    }

    mode = cmds.radioButtonGrp("rb_mode", q=True, select=True)
    collect_all = (mode == 1)

    export_textures(options, meta, collect_all)

# ==========================================================
# UI
# ==========================================================
def build_ui():
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)

    cmds.window(WINDOW, title="Texture UV Animation Export", sizeable=False)
    cmds.columnLayout(adj=True, rowSpacing=6)

    cmds.text(label="1. Select geometry")
    cmds.separator(h=6)

    cmds.text(label="Export Values")
    cmds.checkBox("cb_img", label="Active Image", v=True)
    cmds.checkBox("cb_ou",  label="Offset U", v=True)
    cmds.checkBox("cb_ov",  label="Offset V", v=True)
    cmds.checkBox("cb_su",  label="Scale U", v=True)
    cmds.checkBox("cb_sv",  label="Scale V", v=True)
    cmds.checkBox("cb_r",   label="Rotate UV", v=True)

    cmds.separator(h=6)
    cmds.text(label="Metadata")
    cmds.checkBox("cb_geo",  label="Geometry", v=True)
    cmds.checkBox("cb_mat",  label="Material", v=True)
    cmds.checkBox("cb_file", label="File Texture", v=True)

    cmds.separator(h=6)
    cmds.radioButtonGrp(
        "rb_mode",
        label="Frames",
        labelArray2=["All Frames", "Changes Only"],
        numberOfRadioButtons=2,
        select=2
    )

    cmds.separator(h=6)
    cmds.text(label="Textures")
    cmds.button(label="Refresh from Selection", command=lambda *_: refresh_texture_list())

    cmds.frameLayout(labelVisible=False)
    cmds.scrollLayout("textureScroll", height=180)
    cmds.columnLayout("textureColumn", adjustableColumn=True)
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.separator(h=6)
    cmds.text(label="Export Path")
    cmds.rowLayout(nc=2, adjustableColumn=1)
    cmds.textField("pathField", editable=False)
    cmds.button(label="Browse", command=lambda *_: browse_path())
    cmds.setParent("..")

    cmds.separator(h=10)
    cmds.button(label="Export CSV", height=30, command=lambda *_: run_export())

    cmds.showWindow(WINDOW)

# ==========================================================
# Run
# ==========================================================
build_ui()
