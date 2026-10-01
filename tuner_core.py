# tuner_core.py
"""
Чистое ядро TunerGUI без GUI.
Парсинг XDF, чтение/запись BIN, вычисление формул, построение дерева.
"""

import ast
import operator
import re
import struct
import xml.etree.ElementTree as ET


# ============================================================
#  MATH
# ============================================================

_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.Mod: operator.mod,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def eval_equation(equation, x):
    if not equation or equation.strip() in ("", "X"):
        return x
    try:
        node = ast.parse(equation, mode="eval").body
    except SyntaxError:
        return x

    def _ev(n):
        if isinstance(n, ast.Expression): return _ev(n.body)
        if isinstance(n, ast.Constant): return float(n.value)
        if isinstance(n, ast.Name):
            if n.id == "X": return float(x)
            raise ValueError(n.id)
        if isinstance(n, ast.BinOp):
            op = _BINOPS.get(type(n.op))
            if not op: raise ValueError("op")
            return op(_ev(n.left), _ev(n.right))
        if isinstance(n, ast.UnaryOp):
            op = _UNARY.get(type(n.op))
            if not op: raise ValueError("unary")
            return op(_ev(n.operand))
        raise ValueError(type(n).__name__)

    try:
        return _ev(node)
    except Exception:
        return x


def raw_from_engineering(equation, y):
    if not equation or equation.strip() in ("", "X"):
        return y
    eq = equation.replace(" ", "")

    m = re.fullmatch(r"X/([\d.]+)", eq)
    if m: return y * float(m.group(1))
    m = re.fullmatch(r"X\*([\d.]+)", eq)
    if m: return y / float(m.group(1))
    m = re.fullmatch(r"X/([\d.]+)\*([\d.]+)", eq)
    if m:
        a, b = map(float, m.groups()); return y * a / b
    m = re.fullmatch(r"X\*([\d.]+)\*([\d.]+)", eq)
    if m:
        a, b = map(float, m.groups()); return y / (a * b)
    m = re.fullmatch(r"X/([\d.]+)\*([\d.]+)\+([\d.]+)", eq)
    if m:
        a, b, c = map(float, m.groups()); return (y - c) * a / b
    m = re.fullmatch(r"X/([\d.]+)\*([\d.]+)-([\d.]+)", eq)
    if m:
        a, b, c = map(float, m.groups()); return (y + c) * a / b
    m = re.fullmatch(r"X\*([\d.]+)\+([\d.]+)", eq)
    if m:
        a, b = map(float, m.groups()); return (y - b) / a
    m = re.fullmatch(r"X/([\d.]+)-\(?([\d.]+)\)?", eq)
    if m:
        a, b = map(float, m.groups()); return (y + b) * a

    lo, hi = -1e9, 1e9
    for _ in range(200):
        mid = (lo + hi) / 2
        if eval_equation(equation, mid) < y: lo = mid
        else: hi = mid
    return (lo + hi) / 2


# ============================================================
#  XDF PARSER
# ============================================================

def _struct_from_typeflags(flags_str, size_bits, min_val=None, max_val=None):
    flags = 0
    if flags_str:
        try:
            flags = int(flags_str, 0)
        except (TypeError, ValueError):
            flags = 0
    is_signed = bool(flags & 0x04)
    if not is_signed and min_val is not None and min_val < 0:
        is_signed = True
    if size_bits == 8:  return "b" if is_signed else "B"
    if size_bits == 16: return "h" if is_signed else "H"
    if size_bits == 32: return "i" if is_signed else "I"
    if size_bits == 64: return "q" if is_signed else "Q"
    return "B"


def _parse_int(s, default=0):
    if s is None: return default
    try: return int(s, 0)
    except (TypeError, ValueError): return default


def _parse_float(s, default=None):
    if s is None: return default
    try: return float(s)
    except (TypeError, ValueError): return default


def _embedded(elem, min_val=None, max_val=None):
    ed = elem.find("EMBEDDEDDATA")
    if ed is None:
        return None
    size_bits = _parse_int(ed.get("mmedelementsizebits"), 8)
    flags = ed.get("mmedtypeflags")
    addr_s = ed.get("mmedaddress")
    return {
        "address": _parse_int(addr_s, None) if addr_s is not None else None,
        "size_bits": size_bits,
        "typeflags": flags,
        "fmt": _struct_from_typeflags(flags, size_bits, min_val, max_val),
        "rows": _parse_int(ed.get("mmedrowcount"), 1),
        "cols": _parse_int(ed.get("mmedcolcount"), 1),
        "major_stride_bits": _parse_int(ed.get("mmedmajorstridebits"), 0),
        "minor_stride_bits": _parse_int(ed.get("mmedminorstridebits"), 0),
    }


def _math(elem):
    m = elem.find("MATH")
    eq = m.get("equation") if m is not None else None
    units = (elem.findtext("units") or "").strip()
    return (eq or "X"), units


def _labels(elem):
    return [lbl.get("value", "0") for lbl in elem.findall("LABEL")]


def _categories_mem(elem):
    out = []
    for cm in elem.findall("CATEGORYMEM"):
        idx = _parse_int(cm.get("index", "0"), 0)
        cid = _parse_int(cm.get("category", "0"), 0)
        out.append((idx, cid))
    out.sort(key=lambda x: x[0])
    return out


def _clean_xml_bytes(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    # пробуем UTF-8, иначе latin-1
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text


def parse_xdf(data: bytes) -> dict:
    text = _clean_xml_bytes(data)
    root = ET.fromstring(text)

    defaults_lsb = 0
    d = root.find(".//DEFAULTS")
    if d is not None:
        defaults_lsb = _parse_int(d.get("lsbfirst"), 0)
    endian = "<" if defaults_lsb else ">"

    categories = {}
    category_order = []
    for cat in root.findall(".//CATEGORY"):
        raw_idx = (cat.get("index", "0") or "0").lower().replace("0x", "").strip()
        try:
            cid = int(raw_idx, 16)
        except ValueError:
            cid = 0
        name = (cat.get("name") or f"Category{cid}").strip()
        if cid not in categories:
            category_order.append(cid)
        categories[cid] = name

    tables = {}
    constants = {}
    seq = 0

    for tbl in root.findall(".//XDFTABLE"):
        try:
            title = (tbl.findtext("title") or "Unnamed").strip()
            desc = (tbl.findtext("description") or "").strip()
            axes = {ax.get("id"): ax for ax in tbl.findall("XDFAXIS")}
            if "z" not in axes:
                continue

            z_min = _parse_float(axes["z"].findtext("min"))
            z_max = _parse_float(axes["z"].findtext("max"))
            z_ed = _embedded(axes["z"], min_val=z_min, max_val=z_max)
            if not z_ed or z_ed["address"] is None:
                continue

            z_eq, z_units = _math(axes["z"])
            z_dec = _parse_int(axes["z"].findtext("decimalpl"), 0)
            rows = z_ed["rows"] or 1
            cols = z_ed["cols"] or 1

            def make_axis(ax_id):
                if ax_id not in axes:
                    return None
                ax = axes[ax_id]
                a_min = _parse_float(ax.findtext("min"))
                a_max = _parse_float(ax.findtext("max"))
                ed = _embedded(ax, min_val=a_min, max_val=a_max)
                eq, units = _math(ax)
                a = {
                    "id": ax_id, "equation": eq, "units": units,
                    "indexcount": _parse_int(ax.findtext("indexcount"), 1),
                    "decimalpl": _parse_int(ax.findtext("decimalpl"), 0),
                    "labels": _labels(ax),
                    "address": None, "fmt": None, "size_bits": None,
                }
                if ed:
                    a["address"] = ed["address"]
                    a["fmt"] = ed["fmt"]
                    a["size_bits"] = ed["size_bits"]
                return a

            cats_list = _categories_mem(tbl)
            is_axis = len(cats_list) > 1
            key = title if title not in tables else f"{title}__{seq}"
            tables[key] = {
                "title": title,
                "description": desc,
                "address": z_ed["address"],
                "fmt": z_ed["fmt"],
                "size_bits": z_ed["size_bits"],
                "rows": rows, "cols": cols,
                "major_stride_bits": z_ed["major_stride_bits"],
                "minor_stride_bits": z_ed["minor_stride_bits"],
                "equation": z_eq, "units": z_units, "decimalpl": z_dec,
                "endian": endian,
                "x_axis": make_axis("x"),
                "y_axis": make_axis("y"),
                "categories": cats_list,
                "is_axis": is_axis,
                "_seq": seq,
            }
            seq += 1
        except Exception:
            continue

    for c in root.findall(".//XDFCONSTANT"):
        try:
            title = (c.findtext("title") or "Unnamed").strip()
            desc = (c.findtext("description") or "").strip()
            c_min = _parse_float(c.findtext("min"))
            c_max = _parse_float(c.findtext("max"))
            ed = _embedded(c, min_val=c_min, max_val=c_max)
            if not ed or ed["address"] is None:
                continue
            eq, units = _math(c)
            cats_list = _categories_mem(c)
            is_axis = len(cats_list) > 1
            key = title if title not in constants else f"{title}__{seq}"
            constants[key] = {
                "title": title, "description": desc,
                "address": ed["address"], "fmt": ed["fmt"],
                "size_bits": ed["size_bits"],
                "equation": eq, "units": units,
                "decimalpl": _parse_int(c.findtext("decimalpl"), 0),
                "endian": endian,
                "categories": cats_list,
                "is_axis": is_axis,
                "_seq": seq,
            }
            seq += 1
        except Exception:
            continue

    axis_cat_id = None
    for cid, name in categories.items():
        if name.strip().lower() == "axis":
            axis_cat_id = cid
            break

    return {
        "tables": tables,
        "constants": constants,
        "endian": endian,
        "categories": categories,
        "category_order": category_order,
        "axis_cat_id": axis_cat_id,
    }


# ============================================================
#  BIN READ / WRITE
# ============================================================

def _read_raw(data, address, fmt, endian=">"):
    size = struct.calcsize(endian + fmt)
    if address < 0 or address + size > len(data):
        return None
    return struct.unpack_from(endian + fmt, data, address)[0]


def _write_raw(data, address, fmt, value, endian=">"):
    size = struct.calcsize(endian + fmt)
    if address < 0 or address + size > len(data):
        return False
    if fmt in ("f", "d"):
        v = float(value)
    else:
        v = int(round(float(value)))
        if fmt == "B":   v = max(0, min(255, v))
        elif fmt == "b": v = max(-128, min(127, v))
        elif fmt == "H": v = max(0, min(65535, v))
        elif fmt == "h": v = max(-32768, min(32767, v))
        elif fmt == "I": v = max(0, min(2**32 - 1, v))
        elif fmt == "i": v = max(-(2**31), min(2**31 - 1, v))
    try:
        struct.pack_into(endian + fmt, data, address, v)
    except struct.error:
        return False
    return True


def _cell_offset(table, r, c):
    endian = table.get("endian", ">")
    size_bytes = struct.calcsize(endian + table["fmt"])
    major = table.get("major_stride_bits", 0) or (table["cols"] * size_bytes * 8)
    minor = table.get("minor_stride_bits", 0) or (size_bytes * 8)
    major_bytes = abs(major) // 8
    minor_bytes = abs(minor) // 8
    return table["address"] + r * major_bytes + c * minor_bytes


def read_table_eng(bin_data, table):
    rows, cols = table["rows"], table["cols"]
    fmt, eq = table["fmt"], table["equation"]
    endian = table.get("endian", ">")
    out = []
    for r in range(rows):
        row = []
        for c in range(cols):
            off = _cell_offset(table, r, c)
            raw = _read_raw(bin_data, off, fmt, endian)
            row.append(None if raw is None else eval_equation(eq, raw))
        out.append(row)
    return out


def write_table_eng(bin_data, table, eng_values):
    rows, cols = table["rows"], table["cols"]
    fmt, eq = table["fmt"], table["equation"]
    endian = table.get("endian", ">")
    ok = True
    for r in range(rows):
        for c in range(cols):
            if r >= len(eng_values) or c >= len(eng_values[r]):
                continue
            v = eng_values[r][c]
            if v is None:
                continue
            try:
                raw = raw_from_engineering(eq, float(v))
            except (TypeError, ValueError):
                continue
            off = _cell_offset(table, r, c)
            if not _write_raw(bin_data, off, fmt, raw, endian):
                ok = False
    return ok


def read_value_eng(bin_data, address, fmt, equation, endian=">"):
    raw = _read_raw(bin_data, address, fmt, endian)
    if raw is None:
        return None
    return eval_equation(equation, raw)


def write_value_eng(bin_data, address, fmt, equation, eng_value, endian=">"):
    raw = raw_from_engineering(equation, float(eng_value))
    return _write_raw(bin_data, address, fmt, raw, endian)


def read_axis_eng(bin_data, axis, endian=">"):
    if not axis:
        return []
    if axis["labels"]:
        return [eval_equation(axis.get("equation", "X"), float(v))
                if v not in (None, "") else None
                for v in axis["labels"]]
    addr, fmt = axis.get("address"), axis.get("fmt")
    if addr is None or fmt is None:
        return []
    eq = axis.get("equation", "X")
    size = struct.calcsize(endian + fmt)
    n = axis.get("indexcount", 1)
    out = []
    for i in range(n):
        raw = _read_raw(bin_data, addr + i * size, fmt, endian)
        out.append(None if raw is None else eval_equation(eq, raw))
    return out


# ============================================================
#  TREE BUILDING
# ============================================================

def build_tree_json(xdf) -> list:
    """
    Строит вложенное дерево для отображения:
    категории → подпапки → листья (таблицы/константы).
    Сортировка как в TunerPro:
      группа 0: [Custom Code] ...
      группа 1: [Axis] ...
      группа 2: обычные категории
      группа 3: листья
    Внутри группы — по алфавиту.
    """
    cats = xdf["categories"]
    axis_cids = {cid for cid, name in cats.items()
                 if name.strip().lower() == "axis"}

    # Корневой узел
    root = {"children": []}
    # Хранилище узлов по path (tuple of cid)
    node_by_path = {}

    def get_or_create_node(path):
        if not path:
            return root
        if path in node_by_path:
            return node_by_path[path]
        parent = get_or_create_node(path[:-1])
        cid = path[-1]
        node = {
            "type": "axis" if cid in axis_cids else "category",
            "text": cats.get(cid, f"Category{cid}"),
            "children": [],
            "_cid": cid,
        }
        parent["children"].append(node)
        node_by_path[path] = node
        return node

    def add_leaf(path, leaf):
        parent = get_or_create_node(path)
        parent["children"].append(leaf)

    # Таблицы
    for key, t in xdf["tables"].items():
        raw = sorted(t.get("categories", []), key=lambda x: x[0])
        path = tuple(cid - 1 for _, cid in raw)
        is_axis_item = (raw[-1][1] - 1) in axis_cids if raw else False
        add_leaf(path, {
            "type": "leaf",
            "kind": "table",
            "key": key,
            "text": t["title"],
            "is_axis_item": is_axis_item,
        })

    # Константы
    for key, c in xdf["constants"].items():
        raw = sorted(c.get("categories", []), key=lambda x: x[0])
        path = tuple(cid - 1 for _, cid in raw)
        add_leaf(path, {
            "type": "leaf",
            "kind": "constant",
            "key": key,
            "text": c["title"],
            "is_axis_item": False,
        })

    def sort_rec(node):
        def sort_key(n):
            if n["type"] == "leaf":
                g = 3
            elif n["text"].startswith("[Custom Code]"):
                g = 0
            elif n["text"].startswith("[Axis]"):
                g = 1
            else:
                g = 2
            return (g, n["text"].lower())
        node["children"].sort(key=sort_key)
        for ch in node["children"]:
            if "children" in ch:
                sort_rec(ch)

    sort_rec(root)

    # Считаем счётчики (число листьев в поддереве) и убираем служебное
    def count_and_clean(node):
        if node["type"] == "leaf":
            return 1
        total = 0
        for ch in node["children"]:
            total += count_and_clean(ch)
        node["count"] = total
        node.pop("_cid", None)
        return total

    for ch in root["children"]:
        count_and_clean(ch)

    return root["children"]


def get_all_leaves(xdf) -> list:
    """
    Плоский список (key, kind, path_str).
    На случай, если понадобится selectbox.
    """
    out = []
    cats = xdf["categories"]
    for key, t in xdf["tables"].items():
        raw = sorted(t.get("categories", []), key=lambda x: x[0])
        path_str = " → ".join(cats.get(cid - 1, "?") for _, cid in raw)
        out.append((key, "table", path_str))
    for key, c in xdf["constants"].items():
        raw = sorted(c.get("categories", []), key=lambda x: x[0])
        path_str = " → ".join(cats.get(cid - 1, "?") for _, cid in raw)
        out.append((key, "constant", path_str))
    return out