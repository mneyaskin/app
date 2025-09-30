import streamlit as st
import pandas as pd
import numpy as np
import os
from io import StringIO
import base64

st.set_page_config(
    page_title="CSV Column Filter",
    page_icon="📊",
    layout="wide"
)

def auto_select_columns(columns):
    """Автоматически выбирает нужные столбцы если они есть в файле"""
    target_columns = [
        "Time [ms]",
        "Engine Speed (RPM) [1/min]", 
        "Vehicle Speed [km/h]"
    ]
    
    selected_columns = []
    
    # Ищем целевые столбцы в доступных колонках
    for col in columns:
        if col in target_columns:
            selected_columns.append(col)
    
    return selected_columns

def auto_set_last_row_settings(columns):
    """Автоматически настраивает обрезку по столбцу Engine Speed"""
    target_column = "Engine Speed (RPM) [1/min]"
    
    if target_column in columns:
        return {
            'method': 'column',
            'column': target_column,
            'operator': '>=',
            'value': '1'
        }
    return {'method': 'none'}

def get_download_link(df, filename):
    """Генерирует ссылку для скачивания CSV файла"""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-align: center; text-decoration: none; display: inline-block; border-radius: 4px;">📥 Скачать обработанный файл</a>'
    return href

def main():
    st.title("📊 CSV Column Filter")
    st.markdown("Загрузите CSV файл для фильтрации столбцов и обработки данных")
    
    # Инициализация session state
    if 'uploaded_file' not in st.session_state:
        st.session_state.uploaded_file = None
    if 'df_original' not in st.session_state:
        st.session_state.df_original = None
    if 'selected_columns' not in st.session_state:
        st.session_state.selected_columns = []
    if 'rename_map' not in st.session_state:
        st.session_state.rename_map = {}
    
    # Загрузка файла
    uploaded_file = st.file_uploader(
        "Выберите CSV файл",
        type=['csv'],
        help="Перетащите файл или нажмите для выбора"
    )
    
    if uploaded_file is not None:
        st.session_state.uploaded_file = uploaded_file
        
        try:
            # Чтение файла
            df = pd.read_csv(uploaded_file)
            st.session_state.df_original = df
            
            # Получение колонок
            columns = list(df.columns)
            
            # Автоматический выбор столбцов
            auto_selected = auto_select_columns(columns)
            st.session_state.selected_columns = auto_selected
            
            # Автоматическая настройка обрезки
            auto_settings = auto_set_last_row_settings(columns)
            
            st.success(f"✅ Файл успешно загружен: {uploaded_file.name}")
            st.write(f"**Размер данных:** {df.shape[0]} строк, {df.shape[1]} колонок")
            
            # Основные вкладки
            tab1, tab2, tab3 = st.tabs(["📋 Выбор столбцов", "✏️ Переименование", "✂️ Обрезка данных"])
            
            with tab1:
                st.header("Выбор столбцов для сохранения")
                
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.subheader("Доступные столбцы")
                    all_columns = st.multiselect(
                        "Выберите столбцы для сохранения:",
                        options=columns,
                        default=auto_selected,
                        key="columns_multiselect"
                    )
                    
                with col2:
                    st.subheader("Ручной ввод")
                    st.markdown("Или введите точные названия столбцов (через запятую):")
                    manual_columns = st.text_input(
                        "Столбцы:",
                        value=", ".join(auto_selected),
                        key="manual_columns"
                    )
                
                # Объединение выбранных колонок
                if manual_columns.strip():
                    manual_list = [col.strip() for col in manual_columns.split(',') if col.strip()]
                    combined_columns = list(set(all_columns + manual_list))
                else:
                    combined_columns = all_columns
                
                st.session_state.selected_columns = combined_columns
                
                if combined_columns:
                    st.info(f"**Выбрано столбцов:** {len(combined_columns)}")
                    st.write("Выбранные столбцы:", ", ".join(combined_columns))
                else:
                    st.warning("⚠️ Не выбрано ни одного столбца")
            
            with tab2:
                st.header("Переименование столбцов")
                
                if st.session_state.selected_columns:
                    st.markdown("Укажите новые названия для столбцов (оставьте пустым для сохранения оригинального названия):")
                    
                    rename_map = {}
                    for i, col in enumerate(st.session_state.selected_columns):
                        col1, col2 = st.columns([1, 2])
                        with col1:
                            st.text_input(
                                f"Столбец {i+1} (оригинал):",
                                value=col,
                                key=f"orig_{i}",
                                disabled=True
                            )
                        with col2:
                            new_name = st.text_input(
                                f"Новое название для столбца {i+1}:",
                                value=col,
                                key=f"new_{i}"
                            )
                            if new_name and new_name != col:
                                rename_map[col] = new_name
                    
                    st.session_state.rename_map = rename_map
                    
                    if rename_map:
                        st.success("**Изменения переименования:**")
                        for orig, new in rename_map.items():
                            st.write(f"`{orig}` → `{new}`")
                else:
                    st.warning("Сначала выберите столбцы во вкладке 'Выбор столбцов'")
            
            with tab3:
                st.header("Определение последней строки")
                
                st.radio(
                    "Метод определения последней строки:",
                    options=["none", "column", "manual"],
                    format_func=lambda x: {
                        "none": "Не обрезать",
                        "column": "По условию в столбце", 
                        "manual": "По ручному значению"
                    }[x],
                    key="last_row_method",
                    index=["none", "column", "manual"].index(auto_settings['method'])
                )
                
                if st.session_state.last_row_method == "column":
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    with col1:
                        st.selectbox(
                            "Столбец:",
                            options=st.session_state.selected_columns,
                            key="last_row_column",
                            index=st.session_state.selected_columns.index(auto_settings['column']) if auto_settings['column'] in st.session_state.selected_columns else 0
                        )
                    
                    with col2:
                        operators = ["==", "!=", ">", ">=", "<", "<="]
                        st.selectbox(
                            "Условие:",
                            options=operators,
                            key="condition_operator",
                            index=operators.index(auto_settings['operator'])
                        )
                    
                    with col3:
                        st.text_input(
                            "Значение:",
                            value=auto_settings['value'],
                            key="condition_value"
                        )
                
                elif st.session_state.last_row_method == "manual":
                    st.text_input(
                        "Значение для поиска (первое вхождение в любом столбце):",
                        key="manual_value"
                    )
            
            # Кнопка обработки
            st.markdown("---")
            if st.button("🚀 Обработать и скачать файл", type="primary", use_container_width=True):
                if not st.session_state.selected_columns:
                    st.error("❌ Не выбрано ни одного столбца")
                    return
                
                try:
                    # Фильтрация столбцов
                    filtered_df = df[st.session_state.selected_columns].copy()
                    
                    # Применение переименования
                    if st.session_state.rename_map:
                        filtered_df = filtered_df.rename(columns=st.session_state.rename_map)
                    
                    # Обработка последней строки
                    last_row_info = ""
                    method = st.session_state.last_row_method
                    
                    if method == "column":
                        last_row_column = st.session_state.last_row_column
                        condition_value = st.session_state.condition_value.strip()
                        operator = st.session_state.condition_operator
                        
                        if last_row_column and condition_value:
                            try:
                                # Конвертация в числовой формат если возможно
                                try:
                                    numeric_series = pd.to_numeric(filtered_df[last_row_column], errors='raise')
                                    condition_val = float(condition_value)
                                except ValueError:
                                    # Если не числовой, сравниваем как строки
                                    numeric_series = filtered_df[last_row_column].astype(str)
                                    condition_val = condition_value
                                
                                # Создание условия
                                if operator == "==":
                                    mask = numeric_series == condition_val
                                elif operator == "!=":
                                    mask = numeric_series != condition_val
                                elif operator == ">":
                                    mask = numeric_series > condition_val
                                elif operator == ">=":
                                    mask = numeric_series >= condition_val
                                elif operator == "<":
                                    mask = numeric_series < condition_val
                                elif operator == "<=":
                                    mask = numeric_series <= condition_val
                                
                                # Поиск первой строки удовлетворяющей условию
                                first_match_idx = mask.idxmax() if mask.any() else None
                                
                                if first_match_idx is not None:
                                    filtered_df = filtered_df.loc[:first_match_idx]
                                    matched_value = filtered_df[last_row_column].iloc[first_match_idx]
                                    last_row_info = f"Последняя строка определена по условию '{last_row_column} {operator} {condition_value}' (найдено значение: {matched_value})"
                                else:
                                    st.error(f"❌ Не найдено строк, удовлетворяющих условию '{last_row_column} {operator} {condition_value}'")
                                    return
                                    
                            except Exception as e:
                                st.error(f"❌ Ошибка при обработке условия: {str(e)}")
                                return
                    
                    elif method == "manual":
                        manual_value = st.session_state.manual_value.strip()
                        if manual_value:
                            try:
                                mask = (filtered_df.astype(str) == manual_value).any(axis=1)
                                if not mask.any():
                                    st.error(f"❌ Значение '{manual_value}' не найдено в таблице")
                                    return
                                
                                first_idx = mask.idxmax()
                                filtered_df = filtered_df.loc[:first_idx]
                                last_row_info = f"Последняя строка определена по первому вхождению значения '{manual_value}'"
                                
                            except Exception as e:
                                st.error(f"❌ Ошибка при поиске значения '{manual_value}': {str(e)}")
                                return
                    
                    # Показ результатов
                    st.success("✅ Файл успешно обработан!")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Исходных строк", df.shape[0])
                    with col2:
                        st.metric("Результирующих строк", len(filtered_df))
                    with col3:
                        st.metric("Столбцов", len(filtered_df.columns))
                    
                    # Информация о переименовании
                    if st.session_state.rename_map:
                        st.info("**Переименованные столбцы:**")
                        for orig, new in st.session_state.rename_map.items():
                            st.write(f"`{orig}` → `{new}`")
                    
                    # Информация об обрезке
                    if last_row_info:
                        st.info(f"**{last_row_info}**")
                    
                    # Предпросмотр данных
                    with st.expander("👀 Предпросмотр обработанных данных"):
                        st.dataframe(filtered_df.head(10))
                    
                    # Ссылка для скачивания
                    original_name = os.path.splitext(uploaded_file.name)[0]
                    output_filename = f"{original_name}_filtered.csv"
                    
                    st.markdown(get_download_link(filtered_df, output_filename), unsafe_allow_html=True)
                    
                except Exception as e:
                    st.error(f"❌ Произошла ошибка при обработке файла: {str(e)}")
        
        except Exception as e:
            st.error(f"❌ Ошибка при чтении файла: {str(e)}")
    
    else:
        st.info("📁 Пожалуйста, загрузите CSV файл для начала работы")
        
        # Пример структуры файла
        with st.expander("ℹ️ Требования к файлу"):
            st.markdown("""
            Файл должен содержать CSV данные с колонками. Рекомендуемые колонки:
            - `Time [ms]` - время в миллисекундах
            - `Engine Speed (RPM) [1/min]` - обороты двигателя
            - `Vehicle Speed [km/h]` - скорость автомобиля
            
            Приложение автоматически определит эти колонки если они присутствуют в файле.
            """)

if __name__ == "__main__":
    main()