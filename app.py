# app.py
"""
TunerGUI Web — Streamlit-версия.
Запуск:
    pip install -r requirements.txt
    python -m streamlit run app.py
"""

import pandas as pd
import streamlit as st

import tuner_core as core


# ============================================================
#  НАСТРОЙКИ СТРАНИЦЫ
# ============================================================

st.set_page_config(
    page_title="TunerGUI Web",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
#  SESSION STATE
# ============================================================

if "xdf" not in st.session_state:
    st.session_state.xdf = None
    st.session_state.xdf_name = None

if "bin_data" not in st.session_state:
    st.session_state.bin_data = None
    st.session_state.bin_name = None

if "modified" not in st.session_state:
    st.session_state.modified = False


# ============================================================
#  QUERY PARAM
# ============================================================

def get_query_param(name):
    try:
        v = st.query_params.get(name)
    except AttributeError:
        v = st.experimental_get_query_params().get(name)
        if isinstance(v, list):
            v = v[0] if v else None
    return v


def set_query_param(name, value):
    try:
        st.query_params[name] = value
    except AttributeError:
        params = st.experimental_get_query_params()
        params[name] = value
        st.experimental_set_query_params(**params)


# ============================================================
#  CSS
# ============================================================

st.markdown("""
<style>
.block-container { padding-top: 1rem; padding-bottom: 1rem; }
h1 { font-size: 1.6rem !important; margin-bottom: 0.4rem !important; }
h2 { font-size: 1.2rem !important; margin-top: 0.6rem !important; }
.stDataFrame td { font-family: monospace; }
div[data-baseweb="select"] {
    font-family: 'Consolas', 'Courier New', monospace;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
#  ЗАГРУЗКА ФАЙЛОВ
# ============================================================

st.markdown("# 🔧 TunerGUI Web")

col_xdf, col_bin = st.columns(2)

with col_xdf:
    xdf_file = st.file_uploader(
        "XDF файл",
        type=["xdf", "txt", "xml"],
        key="xdf_uploader",
    )
    if xdf_file is not None and st.session_state.xdf_name != xdf_file.name:
        with st.spinner("Парсинг XDF..."):
            data = xdf_file.read()
            try:
                st.session_state.xdf = core.parse_xdf(data)
                st.session_state.xdf_name = xdf_file.name
                st.success(
                    f"XDF загружен: {len(st.session_state.xdf['tables'])} таблиц, "
                    f"{len(st.session_state.xdf['constants'])} констант"
                )
            except Exception as e:
                st.error(f"Ошибка парсинга XDF: {e}")

with col_bin:
    bin_file = st.file_uploader(
        "BIN файл",
        type=["bin"],
        key="bin_uploader",
    )
    if bin_file is not None and st.session_state.bin_name != bin_file.name:
        data = bin_file.read()
        st.session_state.bin_data = bytearray(data)
        st.session_state.bin_name = bin_file.name
        st.session_state.modified = False
        st.success(f"BIN загружен: {len(data)} байт")


# ============================================================
#  ОСНОВНОЙ UI
# ============================================================

if st.session_state.xdf is None or st.session_state.bin_data is None:
    st.info("Загрузите XDF и BIN, чтобы начать работу.")
    st.stop()


col_tree, col_editor = st.columns([1, 2], gap="medium")


# ============================================================
#  ЛЕВАЯ КОЛОНКА — ДЕРЕВО В SELECTBOX
# ============================================================

with col_tree:
    st.markdown("### Дерево элементов")

    xdf = st.session_state.xdf

    tree_data = core.build_tree_json(xdf)

    ICON_CAT = "📁"
    ICON_AXIS = "⚙"
    ICON_TABLE = "📊"
    ICON_CONST = "🔢"
    INDENT = "    "  # 4 пробела на уровень

    lines = []  # (label, key_or_None, kind, description_lower)

    def walk(node, depth):
        indent = INDENT * depth
        if node["type"] == "leaf":
            icon = ICON_CONST if node["kind"] == "constant" else ICON_TABLE
            label = f"{indent}{icon} {node['text']}"
            if node["kind"] == "constant":
                item = xdf["constants"].get(node["key"], {})
            else:
                item = xdf["tables"].get(node["key"], {})
            desc = (item.get("description") or "").lower()
            lines.append((label, node["key"], node["kind"], desc))
        else:
            is_axis = node["type"] == "axis"
            icon = ICON_AXIS if is_axis else ICON_CAT
            count = node.get("count", 0)
            label = f"{indent}{icon} {node['text']} ({count})"
            lines.append((label, None, "category", ""))
            for ch in node.get("children", []):
                walk(ch, depth + 1)

    for root_node in tree_data:
        walk(root_node, 0)

    # ---- Поиск: по title ИЛИ по description ----
    search = st.text_input(
        "Поиск",
        key="search_tree",
        placeholder="Найти по названию или описанию...",
    )

    if search:
        q = search.lower()
        lines = [
            (lbl, key, kind, desc)
            for (lbl, key, kind, desc) in lines
            if q in lbl.lower() or q in desc
        ]

    # ---- selectbox ----
    current_sel = get_query_param("sel") or ""
    labels = [l[0] for l in lines]

    if not labels:
        st.warning("Ничего не найдено.")
    else:
        default_idx = 0
        for i, (lbl, key, kind, desc) in enumerate(lines):
            if key and key == current_sel:
                default_idx = i
                break

        sel_label = st.selectbox(
            "Выберите таблицу или константу",
            labels,
            index=default_idx,
            key="sel_box",
            help=(
                "📁 — категория, ⚙ — подпапка (Axis/Slot), "
                "📊 — таблица, 🔢 — константа. "
                "Выбирайте 📊 или 🔢. "
                "Поиск работает по названию и описанию."
            ),
        )

        for lbl, key, kind, desc in lines:
            if lbl == sel_label:
                if key and key != current_sel:
                    set_query_param("sel", key)
                    st.rerun()
                break

    st.caption(
        "**Легенда:** 📁 категория · ⚙ подпапка · "
        "📊 таблица · 🔢 константа"
    )


# ============================================================
#  ПРАВАЯ КОЛОНКА — РЕДАКТОР
# ============================================================

with col_editor:
    sel_key = get_query_param("sel")

    if not sel_key:
        st.info("Выберите таблицу или константу из списка слева.")
        st.stop()

    xdf = st.session_state.xdf
    bin_data = st.session_state.bin_data

    if sel_key in xdf["tables"]:
        kind = "table"
        item = xdf["tables"][sel_key]
    elif sel_key in xdf["constants"]:
        kind = "constant"
        item = xdf["constants"][sel_key]
    else:
        st.error(f"Элемент не найден: {sel_key}")
        st.stop()

    # ----- ШАПКА -----
    st.markdown(f"## {item['title']}")
    if item.get("description"):
        st.caption(item["description"])

    endian_name = "LE" if item["endian"] == "<" else "BE"
    meta = (
        f"адрес 0x{item['address']:X}  |  "
        f"формула: {item['equation']}  |  "
        f"fmt: {item['fmt']}  |  {endian_name}"
    )
    if item.get("units"):
        meta += f"  |  единицы: {item['units']}"
    if kind == "table":
        meta = f"{item['rows']}×{item['cols']}  |  " + meta
    st.caption(meta)

    # ----- КОНСТАНТА -----
    if kind == "constant":
        val = core.read_value_eng(
            bin_data, item["address"], item["fmt"],
            item["equation"], item["endian"],
        )
        dec = max(0, min(6, int(item["decimalpl"] or 0)))
        col_a, col_b, col_c = st.columns([1, 1, 2])
        with col_a:
            new_val = st.number_input(
                "Значение",
                value=float(val) if val is not None else 0.0,
                format=f"%.{dec}f",
                key="const_val",
            )
        with col_b:
            st.write("")
            st.write("")
            if st.button("Применить к BIN", key="apply_const"):
                ok = core.write_value_eng(
                    bin_data, item["address"], item["fmt"],
                    item["equation"], new_val, item["endian"],
                )
                if ok:
                    st.session_state.modified = True
                    st.success(f"Записано: {new_val}")
                else:
                    st.error("Не удалось записать")

    # ----- ТАБЛИЦА -----
    else:
        grid = core.read_table_eng(bin_data, item)
        x_labels = core.read_axis_eng(bin_data, item["x_axis"], item["endian"])
        y_labels = core.read_axis_eng(bin_data, item["y_axis"], item["endian"])
        if len(x_labels) != item["cols"]:
            x_labels = list(range(item["cols"]))
        if len(y_labels) != item["rows"]:
            y_labels = list(range(item["rows"]))

        x_units = (item["x_axis"] or {}).get("units", "") if item["x_axis"] else ""
        y_units = (item["y_axis"] or {}).get("units", "") if item["y_axis"] else ""

        dec = max(0, min(6, int(item["decimalpl"] or 0)))

        def fmt_num(v):
            if v is None:
                return None
            try:
                return round(float(v), dec)
            except (TypeError, ValueError):
                return None

        def fmt_axis_label(v):
            if v is None:
                return ""
            if isinstance(v, (int, float)):
                return f"{v:g}"
            return str(v)

        # ---- Уникальные имена колонок: X1, X2, ... ----
        cols = [f"X{i+1}" for i in range(len(x_labels))]

        df = pd.DataFrame(
            [[fmt_num(v) for v in row] for row in grid],
            columns=cols,
        )
        index_labels = []
        for yl in y_labels:
            s = fmt_axis_label(yl)
            if y_units:
                s = f"{s} {y_units}"
            index_labels.append(s)
        df.index = index_labels

        # ---- Показываем X-ось над таблицей ----
        x_header_vals = [fmt_axis_label(xl) for xl in x_labels]
        header_text = "  |  ".join(x_header_vals)
        header_label = f"X ({x_units}):" if x_units else "X:"
        st.markdown(
            f"<div style='font-family: monospace; font-size: 12px; "
            f"color: #444; padding: 4px 0; overflow-x: auto; "
            f"white-space: nowrap;'>"
            f"<b>{header_label}</b> {header_text}"
            f"</div>",
            unsafe_allow_html=True,
        )

        if y_units:
            st.caption(f"Y: {y_units}")

        st.markdown("#### Редактирование")

        # ---- column_config: показываем X-ось как label колонок ----
        column_config = {}
        for i, xl in enumerate(x_labels):
            label = fmt_axis_label(xl)
            if x_units:
                label = f"{label} {x_units}"
            column_config[f"X{i+1}"] = st.column_config.NumberColumn(
                label=label,
                format=f"%.{dec}f",
                step=10 ** (-dec) if dec > 0 else 1,
            )

        edited = st.data_editor(
            df,
            use_container_width=True,
            num_rows="fixed",
            key="table_editor",
            height=min(800, 40 + 35 * (item["rows"] + 1)),
            column_config=column_config,
        )

        c1, c2, c3 = st.columns([1, 1, 3])
        with c1:
            apply_btn = st.button("Применить к BIN", key="apply_table")
        with c2:
            if st.button("Перечитать", key="reload_table"):
                st.rerun()

        if apply_btn:
            values = []
            for r in range(edited.shape[0]):
                row = []
                for c in range(edited.shape[1]):
                    v = edited.iat[r, c]
                    if v is None or (isinstance(v, float) and pd.isna(v)):
                        row.append(None)
                    else:
                        row.append(float(v))
                values.append(row)

            ok = core.write_table_eng(bin_data, item, values)
            if ok:
                st.session_state.modified = True
                st.success("Таблица применена")
            else:
                st.error("Не удалось записать")


# ============================================================
#  СКАЧИВАНИЕ BIN
# ============================================================

st.divider()

col_dl, col_status = st.columns([1, 3])
with col_dl:
    fname = st.session_state.bin_name or "modified.bin"
    if fname.endswith(".bin"):
        fname = fname[:-4] + "_modified.bin"
    else:
        fname = fname + "_modified.bin"

    st.download_button(
        "💾 Скачать BIN",
        data=bytes(st.session_state.bin_data),
        file_name=fname,
        mime="application/octet-stream",
        use_container_width=True,
    )

with col_status:
    if st.session_state.modified:
        st.warning("BIN изменён — не забудьте скачать.")
    else:
        st.info("BIN не изменялся.")