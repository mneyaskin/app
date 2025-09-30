import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from io import StringIO
import warnings
warnings.filterwarnings('ignore')

st.set_page_config(
    page_title="Анализатор времени ускорения автомобиля",
    page_icon="🚗",
    layout="wide"
)

def find_crossing_time_with_interpolation(df, target_value, value_column, time_column, direction='up'):
    """Найти время пересечения целевого значения с интерполяцией"""
    values = df[value_column].values
    times = df[time_column].values
    
    if direction == 'up':
        mask = values >= target_value
        if not np.any(mask):
            return None, None, None
        
        first_above_idx = np.argmax(mask)
        if first_above_idx == 0:
            return times[0], values[0], values[0]
        
        value_before = values[first_above_idx - 1]
        value_after = values[first_above_idx]
        time_before = times[first_above_idx - 1]
        time_after = times[first_above_idx]
        
    else:  # direction == 'down'
        mask = values <= target_value
        if not np.any(mask):
            return None, None, None
        
        first_below_idx = np.argmax(mask)
        if first_below_idx == 0:
            return times[0], values[0], values[0]
        
        value_before = values[first_below_idx - 1]
        value_after = values[first_below_idx]
        time_before = times[first_below_idx - 1]
        time_after = times[first_below_idx]
    
    if value_after == value_before:
        return time_before, value_before, value_after
    
    fraction = (target_value - value_before) / (value_after - value_before)
    interpolated_time = time_before + fraction * (time_after - time_before)
    
    return interpolated_time, value_before, value_after

def find_nearest_value(df, target_value, value_column, time_column, direction='up'):
    """Найти ближайшее значение из лога без интерполяции"""
    values = df[value_column].values
    times = df[time_column].values
    
    if direction == 'up':
        mask = values >= target_value
        if not np.any(mask):
            idx = len(values) - 1
            return times[idx], values[idx], values[idx]
        
        first_above_idx = np.argmax(mask)
        
        if first_above_idx > 0:
            dist_prev = abs(values[first_above_idx - 1] - target_value)
            dist_curr = abs(values[first_above_idx] - target_value)
            
            if dist_prev < dist_curr:
                return times[first_above_idx - 1], values[first_above_idx - 1], values[first_above_idx - 1]
        
        return times[first_above_idx], values[first_above_idx], values[first_above_idx]
        
    else:  # direction == 'down'
        mask = values <= target_value
        if not np.any(mask):
            return times[0], values[0], values[0]
        
        first_below_idx = np.argmax(mask)
        
        if first_below_idx > 0:
            dist_prev = abs(values[first_below_idx - 1] - target_value)
            dist_curr = abs(values[first_below_idx] - target_value)
            
            if dist_prev < dist_curr:
                return times[first_below_idx - 1], values[first_below_idx - 1], values[first_below_idx - 1]
        
        return times[first_below_idx], values[first_below_idx], values[first_below_idx]

def calculate_speed_acceleration(df, speed_from, speed_to, use_interpolation=True):
    """Расчет ускорения по диапазону скорости"""
    try:
        df_work = df.copy()
        df_work['Time [s]'] = df_work['Time [ms]'] / 1000.0
        
        if use_interpolation:
            start_time, start_before, start_after = find_crossing_time_with_interpolation(
                df_work, speed_from, 'Vehicle Speed [km/h]', 'Time [s]', 'up'
            )
        else:
            start_time, start_before, start_after = find_nearest_value(
                df_work, speed_from, 'Vehicle Speed [km/h]', 'Time [s]', 'up'
            )
        
        if start_time is None:
            return None
        
        df_after_start = df_work[df_work['Time [s]'] >= start_time]
        if len(df_after_start) == 0:
            return None
        
        if use_interpolation:
            end_time, end_before, end_after = find_crossing_time_with_interpolation(
                df_after_start, speed_to, 'Vehicle Speed [km/h]', 'Time [s]', 'up'
            )
        else:
            end_time, end_before, end_after = find_nearest_value(
                df_after_start, speed_to, 'Vehicle Speed [km/h]', 'Time [s]', 'up'
            )
        
        if end_time is None:
            return None
        
        acceleration_data = df_work[
            (df_work['Time [s]'] >= start_time) & (df_work['Time [s]'] <= end_time)
        ]
        
        if len(acceleration_data) < 2:
            return None
        
        times = acceleration_data['Time [s]'].values
        speeds_ms = acceleration_data['Vehicle Speed [km/h]'].values / 3.6
        
        time_diffs = np.diff(times)
        avg_speeds = (speeds_ms[:-1] + speeds_ms[1:]) / 2
        distance = np.sum(avg_speeds * time_diffs)
        
        acceleration_time = end_time - start_time
        avg_acceleration = (speeds_ms[-1] - speeds_ms[0]) / acceleration_time if acceleration_time > 0 else 0
        
        if use_interpolation:
            actual_speed_from = speed_from
            actual_speed_to = speed_to
        else:
            actual_speed_from = start_after
            actual_speed_to = end_after
        
        return {
            'filename': 'uploaded_file',
            'start_speed': actual_speed_from,
            'end_speed': actual_speed_to,
            'time': acceleration_time,
            'distance': distance,
            'avg_acceleration': avg_acceleration,
            'start_time': start_time,
            'end_time': end_time
        }
        
    except Exception as e:
        st.error(f"Ошибка расчета: {str(e)}")
        return None

def calculate_rpm_acceleration(df, rpm_from, rpm_to, use_interpolation=True):
    """Расчет ускорения по диапазону оборотов"""
    try:
        df_work = df.copy()
        df_work['Time [s]'] = df_work['Time [ms]'] / 1000.0
        
        if use_interpolation:
            start_time, start_before, start_after = find_crossing_time_with_interpolation(
                df_work, rpm_from, 'Engine Speed (RPM) [1/min]', 'Time [s]', 'up'
            )
        else:
            start_time, start_before, start_after = find_nearest_value(
                df_work, rpm_from, 'Engine Speed (RPM) [1/min]', 'Time [s]', 'up'
            )
        
        if start_time is None:
            return None
        
        df_after_start = df_work[df_work['Time [s]'] >= start_time]
        if len(df_after_start) == 0:
            return None
        
        if use_interpolation:
            end_time, end_before, end_after = find_crossing_time_with_interpolation(
                df_after_start, rpm_to, 'Engine Speed (RPM) [1/min]', 'Time [s]', 'up'
            )
        else:
            end_time, end_before, end_after = find_nearest_value(
                df_after_start, rpm_to, 'Engine Speed (RPM) [1/min]', 'Time [s]', 'up'
            )
        
        if end_time is None:
            return None
        
        acceleration_data = df_work[
            (df_work['Time [s]'] >= start_time) & (df_work['Time [s]'] <= end_time)
        ]
        
        if len(acceleration_data) < 2:
            return None
        
        times = acceleration_data['Time [s]'].values
        speeds_ms = acceleration_data['Vehicle Speed [km/h]'].values / 3.6
        
        time_diffs = np.diff(times)
        avg_speeds = (speeds_ms[:-1] + speeds_ms[1:]) / 2
        distance = np.sum(avg_speeds * time_diffs)
        
        acceleration_time = end_time - start_time
        
        if use_interpolation:
            actual_rpm_from = rpm_from
            actual_rpm_to = rpm_to
        else:
            actual_rpm_from = start_after
            actual_rpm_to = end_after
        
        actual_speed_from = np.interp(start_time, df_work['Time [s]'].values, df_work['Vehicle Speed [km/h]'].values)
        actual_speed_to = np.interp(end_time, df_work['Time [s]'].values, df_work['Vehicle Speed [km/h]'].values)
        
        return {
            'filename': 'uploaded_file',
            'start_rpm': actual_rpm_from,
            'end_rpm': actual_rpm_to,
            'start_speed': actual_speed_from,
            'end_speed': actual_speed_to,
            'time': acceleration_time,
            'distance': distance,
            'start_time': start_time,
            'end_time': end_time
        }
        
    except Exception as e:
        st.error(f"Ошибка расчета: {str(e)}")
        return None

def calculate_distance_time(df, start_speed, target_distance, use_interpolation=True):
    """Расчет времени прохождения дистанции с заданной скорости"""
    try:
        df_work = df.copy()
        df_work['Time [s]'] = df_work['Time [ms]'] / 1000.0
        
        if use_interpolation:
            start_time, start_before, start_after = find_crossing_time_with_interpolation(
                df_work, start_speed, 'Vehicle Speed [km/h]', 'Time [s]', 'up'
            )
        else:
            start_time, start_before, start_after = find_nearest_value(
                df_work, start_speed, 'Vehicle Speed [km/h]', 'Time [s]', 'up'
            )
        
        if start_time is None:
            return None
        
        df_after_start = df_work[df_work['Time [s]'] >= start_time].copy()
        if len(df_after_start) < 2:
            return None
        
        times = df_after_start['Time [s]'].values
        speeds_ms = df_after_start['Vehicle Speed [km/h]'].values / 3.6
        
        time_diffs = np.diff(times)
        avg_speeds = (speeds_ms[:-1] + speeds_ms[1:]) / 2
        cumulative_distance = np.cumsum(avg_speeds * time_diffs)
        
        mask = cumulative_distance >= target_distance
        if not np.any(mask):
            return None
        
        target_idx = np.argmax(mask)
        if target_idx == 0:
            return None
        
        dist_before = cumulative_distance[target_idx - 1] if target_idx > 0 else 0
        dist_after = cumulative_distance[target_idx]
        time_before = times[target_idx]
        time_after = times[target_idx + 1]
        
        if dist_after == dist_before:
            end_time = time_before
        else:
            fraction = (target_distance - dist_before) / (dist_after - dist_before)
            end_time = time_before + fraction * (time_after - time_before)
        
        total_time = end_time - start_time
        
        if use_interpolation:
            actual_start_speed = start_speed
        else:
            actual_start_speed = start_after
        
        actual_end_speed = np.interp(end_time, df_work['Time [s]'].values, df_work['Vehicle Speed [km/h]'].values)
        avg_speed_kmh = target_distance / total_time * 3.6 if total_time > 0 else 0
        
        return {
            'filename': 'uploaded_file',
            'start_speed': actual_start_speed,
            'end_speed': actual_end_speed,
            'distance': target_distance,
            'time': total_time,
            'avg_speed': avg_speed_kmh,
            'start_time': start_time,
            'end_time': end_time
        }
        
    except Exception as e:
        st.error(f"Ошибка расчета: {str(e)}")
        return None

def main():
    st.title("🚗 Анализатор времени ускорения автомобиля")
    st.markdown("Загрузите CSV файлы с логами для анализа ускорения")
    
    # Загрузка файлов
    uploaded_files = st.file_uploader(
        "Выберите CSV файлы", 
        type=['csv'], 
        accept_multiple_files=True,
        help="Файлы должны содержать колонки: Vehicle Speed [km/h], Engine Speed (RPM) [1/min], Time [ms]"
    )
    
    dataframes = []
    filenames = []
    
    if uploaded_files:
        for uploaded_file in uploaded_files:
            try:
                df = pd.read_csv(uploaded_file)
                required_columns = ['Vehicle Speed [km/h]', 'Engine Speed (RPM) [1/min]', 'Time [ms]']
                
                if all(col in df.columns for col in required_columns):
                    dataframes.append(df)
                    filenames.append(uploaded_file.name)
                    st.success(f"✅ {uploaded_file.name} - успешно загружен")
                else:
                    st.error(f"❌ {uploaded_file.name} - отсутствуют необходимые колонки")
                    
            except Exception as e:
                st.error(f"❌ Ошибка загрузки {uploaded_file.name}: {str(e)}")
    
    if not dataframes:
        st.info("📁 Пожалуйста, загрузите CSV файлы для начала анализа")
        return
    
    # Настройки
    st.sidebar.header("⚙️ Настройки анализа")
    use_interpolation = st.sidebar.checkbox("Использовать интерполяцию", value=True)
    
    # Вкладки
    tab1, tab2, tab3 = st.tabs([
        "📊 Ускорение по скорости", 
        "⚙️ Ускорение по оборотам", 
        "📏 Дистанция со скорости"
    ])
    
    with tab1:
        st.header("Расчет времени ускорения по скорости")
        
        col1, col2 = st.columns(2)
        with col1:
            speed_from = st.number_input("Начальная скорость (км/ч)", value=100.0, min_value=0.0, step=1.0, key="speed_from")
        with col2:
            speed_to = st.number_input("Конечная скорость (км/ч)", value=150.0, min_value=0.0, step=1.0, key="speed_to")
        
        if st.button("🏁 Рассчитать ускорение по скорости", type="primary"):
            if speed_from >= speed_to:
                st.error("❌ Начальная скорость должна быть меньше конечной")
            else:
                results = []
                
                for i, (df, filename) in enumerate(zip(dataframes, filenames)):
                    result = calculate_speed_acceleration(df, speed_from, speed_to, use_interpolation)
                    
                    if result:
                        results.append([
                            filename,
                            f"{result['start_speed']:.3f}",
                            f"{result['end_speed']:.3f}", 
                            f"{result['time']:.3f}",
                            f"{result['distance']:.3f}",
                            f"{result['avg_acceleration']:.3f}"
                        ])
                    else:
                        results.append([filename, "Нет данных", "Нет данных", "Нет данных", "Нет данных", "Нет данных"])
                
                if results:
                    # Сортировка по времени
                    try:
                        valid_results = [r for r in results if r[3] != "Нет данных"]
                        valid_results.sort(key=lambda x: float(x[3]))
                        invalid_results = [r for r in results if r[3] == "Нет данных"]
                        sorted_results = valid_results + invalid_results
                    except:
                        sorted_results = results
                    
                    # Отображение результатов
                    df_results = pd.DataFrame(sorted_results, columns=[
                        "Файл", "Нач. скорость (км/ч)", "Кон. скорость (км/ч)", 
                        "Время (сек)", "Дистанция (м)", "Ср. ускорение (м/с²)"
                    ])
                    st.dataframe(df_results, use_container_width=True)
                    
                    # График
                    fig = go.Figure()
                    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
                    
                    for i, (df, filename) in enumerate(zip(dataframes, filenames)):
                        df_work = df.copy()
                        df_work['Time [s]'] = df_work['Time [ms]'] / 1000.0
                        fig.add_trace(go.Scatter(
                            x=df_work['Time [s]'], 
                            y=df_work['Vehicle Speed [km/h]'],
                            name=filename,
                            line=dict(width=2, color=colors[i % len(colors)])
                        ))
                    
                    fig.update_layout(
                        title="График скорости от времени",
                        xaxis_title="Время (сек)",
                        yaxis_title="Скорость (км/ч)",
                        height=400,
                        showlegend=True
                    )
                    st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        st.header("Расчет времени ускорения по оборотам")
        
        col1, col2 = st.columns(2)
        with col1:
            rpm_from = st.number_input("Начальные обороты (RPM)", value=2000, min_value=0, step=100, key="rpm_from")
        with col2:
            rpm_to = st.number_input("Конечные обороты (RPM)", value=5000, min_value=0, step=100, key="rpm_to")
        
        if st.button("⚙️ Рассчитать ускорение по оборотам", type="primary"):
            if rpm_from >= rpm_to:
                st.error("❌ Начальные обороты должны быть меньше конечных")
            else:
                results = []
                
                for i, (df, filename) in enumerate(zip(dataframes, filenames)):
                    result = calculate_rpm_acceleration(df, rpm_from, rpm_to, use_interpolation)
                    
                    if result:
                        results.append([
                            filename,
                            f"{result['start_rpm']:.0f}",
                            f"{result['end_rpm']:.0f}",
                            f"{result['start_speed']:.3f}",
                            f"{result['end_speed']:.3f}", 
                            f"{result['time']:.3f}",
                            f"{result['distance']:.3f}"
                        ])
                    else:
                        results.append([filename, "Нет данных", "Нет данных", "Нет данных", "Нет данных", "Нет данных", "Нет данных"])
                
                if results:
                    # Сортировка по времени
                    try:
                        valid_results = [r for r in results if r[5] != "Нет данных"]
                        valid_results.sort(key=lambda x: float(x[5]))
                        invalid_results = [r for r in results if r[5] == "Нет данных"]
                        sorted_results = valid_results + invalid_results
                    except:
                        sorted_results = results
                    
                    df_results = pd.DataFrame(sorted_results, columns=[
                        "Файл", "Нач. RPM", "Кон. RPM", "Нач. скорость (км/ч)",
                        "Кон. скорость (км/ч)", "Время (сек)", "Дистанция (м)"
                    ])
                    st.dataframe(df_results, use_container_width=True)
    
    with tab3:
        st.header("Расчет времени прохождения дистанции")
        
        col1, col2 = st.columns(2)
        with col1:
            distance_speed = st.number_input("Начальная скорость (км/ч)", value=100.0, min_value=0.0, step=1.0, key="dist_speed")
        with col2:
            target_distance = st.number_input("Дистанция (метров)", value=150.0, min_value=0.0, step=10.0, key="target_dist")
        
        if st.button("📏 Рассчитать время дистанции", type="primary"):
            if distance_speed <= 0 or target_distance <= 0:
                st.error("❌ Скорость и дистанция должны быть положительными")
            else:
                results = []
                
                for i, (df, filename) in enumerate(zip(dataframes, filenames)):
                    result = calculate_distance_time(df, distance_speed, target_distance, use_interpolation)
                    
                    if result:
                        results.append([
                            filename,
                            f"{result['start_speed']:.3f}",
                            f"{result['end_speed']:.3f}",
                            f"{result['distance']:.1f}",
                            f"{result['time']:.3f}",
                            f"{result['avg_speed']:.3f}"
                        ])
                    else:
                        results.append([filename, "Нет данных", "Нет данных", "Нет данных", "Нет данных", "Нет данных"])
                
                if results:
                    # Сортировка по времени
                    try:
                        valid_results = [r for r in results if r[4] != "Нет данных"]
                        valid_results.sort(key=lambda x: float(x[4]))
                        invalid_results = [r for r in results if r[4] == "Нет данных"]
                        sorted_results = valid_results + invalid_results
                    except:
                        sorted_results = results
                    
                    df_results = pd.DataFrame(sorted_results, columns=[
                        "Файл", "Нач. скорость (км/ч)", "Кон. скорость (км/ч)", 
                        "Дистанция (м)", "Время (сек)", "Ср. скорость (км/ч)"
                    ])
                    st.dataframe(df_results, use_container_width=True)
    
    # Информация о данных
    with st.expander("📋 Просмотр загруженных данных"):
        selected_file = st.selectbox("Выберите файл для просмотра", filenames)
        if selected_file:
            idx = filenames.index(selected_file)
            df = dataframes[idx]
            st.write(f"**Размер данных:** {df.shape[0]} строк, {df.shape[1]} колонок")
            st.dataframe(df.head(10))
            
            # Базовая статистика
            st.write("**Базовая статистика:**")
            st.write(df[['Vehicle Speed [km/h]', 'Engine Speed (RPM) [1/min]', 'Time [ms]']].describe())

if __name__ == "__main__":
    main()