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
# Helpers: corr-node sampling
# ==========================================================
def _keyword_from_names(file_node, place_node):
    keys = []
    for s in (file_node, place_node):
        if not s:
            continue
        s = s.lower()
        for k in ("iris", "pupil", "eye"):
            if k in s:
                keys.append(k)
    return keys

def get_offset_uv(file_node, place_node):
    keys = _keyword_from_names(file_node, place_node)
    nodes = cmds.ls("Translation_Corr_*", type="multiplyDivide") or []

    for k in keys:
        for n in nodes:
            if k in n.lower():
                return cmds.getAttr(n + ".outputX"), cmds.getAttr(n + ".outputY")

    if nodes:
        return cmds.getAttr(nodes[0] + ".outputX"), cmds.getAttr(nodes[0] + ".outputY")

    return cmds.getAttr(place_node + ".offsetU"), cmds.getAttr(place_node + ".offsetV")

def get_scale_uv(file_node, place_node):
    su = None
    sv = None

    keys = _keyword_from_names(file_node, place_node)

    nodes_u = cmds.ls("ScaleU_corr_*", type="multiplyDivide") or []
    nodes_v = cmds.ls("ScaleV_corr_*", type="multiplyDivide") or []

    for k in keys:
        for n in nodes_u:
            if k in n.lower():
                su = cmds.getAttr(n + ".outputX")
        for n in nodes_v:
            if k in n.lower():
                sv = cmds.getAttr(n + ".outputX")

    if su is None:
        su = cmds.getAttr(place_node + ".repeatU")
    if sv is None:
        sv = cmds.getAttr(place_node + ".repeatV")

    return su, sv

# ==========================================================
# Texture UI
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
def export_textures(options, meta, export_mode, collect_all):
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

            csv_path = os.path.join(base_dir, f"{base_name}_{file_node}.csv")

            rows = []
            curve_frames = []
            curve_values = {opt: [] for opt in options}
            last_state = None

            for f in range(start, end + 1):
                cmds.currentTime(f, edit=True)

                current = {}

                if "ActiveImage" in options:
                    current["ActiveImage"] = get_active_image(file_node)

                if "OffsetU" in options or "OffsetV" in options:
                    ou, ov = get_offset_uv(file_node, place)
                    if "OffsetU" in options:
                        current["OffsetU"] = ou
                    if "OffsetV" in options:
                        current["OffsetV"] = ov

                if "ScaleU" in options or "ScaleV" in options:
                    su, sv = get_scale_uv(file_node, place)
                    if "ScaleU" in options:
                        current["ScaleU"] = su
                    if "ScaleV" in options:
                        current["ScaleV"] = sv

                if "RotateUV" in options:
                    current["RotateUV"] = cmds.getAttr(place + ".rotateUV")

                state = [current[o] for o in options]

                if collect_all or state != last_state:
                    row = [f]
                    if meta["geo"]:
                        row.append(geo)
                    if meta["mat"]:
                        row.append(mat)
                    if meta["file"]:
                        row.append(file_node)
                    for opt in options:
                        row.append(current[opt])
                    rows.append(row)

                    curve_frames.append(f)
                    for opt in options:
                        curve_values[opt].append(current[opt])

                    last_state = state

            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)

                if export_mode == "datatable":
                    header = ["Frame"]
                    if meta["geo"]:
                        header.append("Geometry")
                    if meta["mat"]:
                        header.append("Material")
                    if meta["file"]:
                        header.append("FileTexture")
                    header.extend(options)
                    writer.writerow(header)
                    writer.writerows(rows)
                else:
                    writer.writerow([""] + curve_frames)
                    for opt in options:
                        writer.writerow([opt] + curve_values[opt])

    cmds.inViewMessage(
        amg="<hl>Texture export complete</hl>",
        pos="midCenter",
        fade=True
    )

# ==========================================================
# UI Callbacks & UI
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

    meta = {
        "geo":  cmds.checkBox("cb_geo",  q=True, v=True),
        "mat":  cmds.checkBox("cb_mat",  q=True, v=True),
        "file": cmds.checkBox("cb_file", q=True, v=True)
    }

    export_mode = "datatable" if cmds.radioButtonGrp("rb_export", q=True, select=True) == 1 else "curve"
    collect_all = cmds.radioButtonGrp("rb_frames", q=True, select=True) == 1

    export_textures(options, meta, export_mode, collect_all)

def build_ui():
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)

    cmds.window(WINDOW, title="Texture UV Animation Export", sizeable=False)
    cmds.columnLayout(adj=True, rowSpacing=6)

    cmds.text(label="Export Values")
    cmds.checkBox("cb_img", label="Active Image", v=True)
    cmds.checkBox("cb_ou", label="Offset U", v=True)
    cmds.checkBox("cb_ov", label="Offset V", v=True)
    cmds.checkBox("cb_su", label="Scale U", v=True)
    cmds.checkBox("cb_sv", label="Scale V", v=True)
    cmds.checkBox("cb_r",  label="Rotate UV", v=True)

    cmds.separator(h=6)
    cmds.text(label="Frames")
    cmds.radioButtonGrp(
        "rb_frames",
        labelArray2=["All Frames", "Changes Only"],
        numberOfRadioButtons=2,
        select=1
    )

    cmds.separator(h=6)
    cmds.text(label="Export Type")
    cmds.radioButtonGrp(
        "rb_export",
        labelArray2=["Data Table", "Curve Table"],
        numberOfRadioButtons=2,
        select=1
    )

    cmds.separator(h=6)
    cmds.text(label="Metadata")
    cmds.checkBox("cb_geo",  label="Geometry", v=True)
    cmds.checkBox("cb_mat",  label="Material", v=True)
    cmds.checkBox("cb_file", label="File Texture", v=True)

    cmds.separator(h=6)
    cmds.text(label="Textures")
    cmds.button(label="Refresh from Selection", command=lambda *_: refresh_texture_list())

    cmds.scrollLayout("textureScroll", height=160)
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
