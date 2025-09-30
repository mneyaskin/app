import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import scipy.signal as signal
from io import StringIO
import base64

st.set_page_config(
    page_title="Dyno Graph Analyzer",
    page_icon="📊",
    layout="wide"
)

def calculate_power_and_torque(df, car_mass, drive_loss, power_type, smooth_window):
    """Расчет мощности и момента"""
    df = df.copy()
    
    # Сопротивления
    cd = 0.32
    frontal_area = 2.2
    air_density = 1.225
    c_rr = 0.015
    g = 9.81

    f_roll = c_rr * car_mass * g
    f_aero = 0.5 * air_density * cd * frontal_area * df['speed_mps'] ** 2
    f_acc = car_mass * df['acceleration']
    total_force = f_roll + f_aero + f_acc

    df['power_watt'] = total_force * df['speed_mps']
    df['power_hp'] = df['power_watt'] / 735.5
    df['torque_nm'] = (df['power_hp'] * 735.5 * 60) / (2 * np.pi * df['rpm'])

    # Сглаживание
    if smooth_window % 2 == 0:
        smooth_window += 1
    
    if len(df) > smooth_window:
        df['smooth_hp'] = signal.savgol_filter(df['power_hp'], window_length=smooth_window, polyorder=2)
        df['smooth_tq'] = signal.savgol_filter(df['torque_nm'], window_length=smooth_window, polyorder=2)
        df['smooth_rpm'] = signal.savgol_filter(df['rpm'], window_length=smooth_window, polyorder=2)
    else:
        df['smooth_hp'] = df['power_hp']
        df['smooth_tq'] = df['torque_nm']
        df['smooth_rpm'] = df['rpm']

    # Учет потерь трансмиссии
    if power_type == "crank":
        df['final_hp'] = df['smooth_hp'] / (1 - drive_loss)
        df['final_tq'] = df['smooth_tq'] / (1 - drive_loss)
    else:
        df['final_hp'] = df['smooth_hp']
        df['final_tq'] = df['smooth_tq']

    return df

def main():
    st.title("🚗 Dyno Graph Analyzer")
    st.markdown("Анализ диностенда по данным логов ускорения")
    
    # Инициализация session state
    if 'logs' not in st.session_state:
        st.session_state.logs = []
    if 'colors' not in st.session_state:
        st.session_state.colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
    
    # Загрузка файлов
    uploaded_files = st.file_uploader(
        "Загрузите CSV файлы логов",
        type=['csv'],
        accept_multiple_files=True,
        help="Файлы должны содержать колонки: Time [ms], Engine Speed (RPM) [1/min], Vehicle Speed [km/h]"
    )
    
    if uploaded_files:
        for uploaded_file in uploaded_files:
            if uploaded_file.name not in [log['name'] for log in st.session_state.logs]:
                try:
                    df = pd.read_csv(uploaded_file)
                    # Переименование колонок для удобства
                    df = df.rename(columns={
                        'Time [ms]': 'time_ms',
                        'Engine Speed (RPM) [1/min]': 'rpm',
                        'Vehicle Speed [km/h]': 'speed_kmh'
                    })
                    
                    # Очистка данных
                    df = df.dropna(subset=['time_ms', 'rpm', 'speed_kmh'])
                    df['time_s'] = df['time_ms'] / 1000.0
                    df['speed_mps'] = df['speed_kmh'] / 3.6
                    df['acceleration'] = np.gradient(df['speed_mps'], df['time_s'])
                    
                    # Добавление в session state
                    st.session_state.logs.append({
                        'name': uploaded_file.name,
                        'data': df,
                        'visible': True,
                        'color': st.session_state.colors[len(st.session_state.logs) % len(st.session_state.colors)]
                    })
                    
                    st.success(f"✅ {uploaded_file.name} загружен")
                    
                except Exception as e:
                    st.error(f"❌ Ошибка загрузки {uploaded_file.name}: {str(e)}")
    
    if not st.session_state.logs:
        st.info("📁 Загрузите CSV файлы для начала анализа")
        return
    
    # Панель параметров
    st.sidebar.header("⚙️ Параметры расчета")
    
    car_mass = st.sidebar.slider(
        "Масса авто (кг)",
        min_value=500,
        max_value=3000,
        value=1500,
        step=50
    )
    
    drive_type = st.sidebar.radio(
        "Тип привода",
        options=["fwd", "rwd", "awd"],
        format_func=lambda x: {
            "fwd": "FWD (10% потерь)",
            "rwd": "RWD (15% потерь)", 
            "awd": "AWD (20% потерь)"
        }[x]
    )
    
    drive_losses = {
        "fwd": 0.10,
        "rwd": 0.15, 
        "awd": 0.20
    }
    
    power_type = st.sidebar.radio(
        "Тип мощности",
        options=["wheel", "crank"],
        format_func=lambda x: "WHP (колесо)" if x == "wheel" else "Crank HP (двигатель)"
    )
    
    smooth_window = st.sidebar.slider(
        "Сглаживание",
        min_value=3,
        max_value=99,
        value=15,
        step=2,
        help="Размер окна для сглаживания Савицкого-Голея"
    )
    
    # Чекбоксы для выбора отображаемых логов
    st.sidebar.header("👁️ Отображение логов")
    for i, log in enumerate(st.session_state.logs):
        log['visible'] = st.sidebar.checkbox(
            log['name'],
            value=log['visible'],
            key=f"visible_{i}"
        )
    
    # Расчет данных
    processed_logs = []
    for log in st.session_state.logs:
        if log['visible']:
            try:
                processed_df = calculate_power_and_torque(
                    log['data'], car_mass, drive_losses[drive_type], power_type, smooth_window
                )
                
                # Нахождение пиковых значений
                max_hp_idx = processed_df['final_hp'].idxmax()
                max_tq_idx = processed_df['final_tq'].idxmax()
                
                processed_logs.append({
                    'name': log['name'],
                    'data': processed_df,
                    'color': log['color'],
                    'max_hp': {
                        'value': processed_df['final_hp'].iloc[max_hp_idx],
                        'rpm': processed_df['smooth_rpm'].iloc[max_hp_idx]
                    },
                    'max_tq': {
                        'value': processed_df['final_tq'].iloc[max_tq_idx],
                        'rpm': processed_df['smooth_rpm'].iloc[max_tq_idx]
                    }
                })
            except Exception as e:
                st.error(f"❌ Ошибка обработки {log['name']}: {str(e)}")
    
    if not processed_logs:
        st.warning("⚠️ Нет выбранных логов для отображения")
        return
    
    # Создание графика
    fig = make_subplots(
        specs=[[{"secondary_y": True}]]
    )
    
    # Добавление данных на график
    for log in processed_logs:
        df = log['data']
        
        # Мощность (основная ось Y)
        fig.add_trace(
            go.Scatter(
                x=df['smooth_rpm'],
                y=df['final_hp'],
                name=f"{log['name']} - HP",
                line=dict(color=log['color'], width=2),
                hovertemplate=(
                    "RPM: %{x:.0f}<br>" +
                    "Мощность: %{y:.1f} HP<br>" +
                    "Момент: %{customdata:.1f} Nm<br>" +
                    "<extra></extra>"
                ),
                customdata=df['final_tq']
            ),
            secondary_y=False
        )
        
        # Момент (вторичная ось Y)
        fig.add_trace(
            go.Scatter(
                x=df['smooth_rpm'],
                y=df['final_tq'],
                name=f"{log['name']} - TQ",
                line=dict(color=log['color'], width=2, dash='dash'),
                hovertemplate=(
                    "RPM: %{x:.0f}<br>" +
                    "Момент: %{y:.1f} Nm<br>" +
                    "Мощность: %{customdata:.1f} HP<br>" +
                    "<extra></extra>"
                ),
                customdata=df['final_hp'],
                showlegend=False
            ),
            secondary_y=True
        )
        
        # Пики мощности
        fig.add_trace(
            go.Scatter(
                x=[log['max_hp']['rpm']],
                y=[log['max_hp']['value']],
                mode='markers+text',
                marker=dict(size=10, color=log['color'], symbol='circle'),
                text=[f"{log['max_hp']['value']:.1f} HP"],
                textposition="top center",
                name=f"{log['name']} - Max HP",
                showlegend=False,
                hovertemplate=(
                    f"Пик мощности<br>" +
                    "RPM: %{x:.0f}<br>" +
                    "Мощность: %{y:.1f} HP<br>" +
                    "<extra></extra>"
                )
            ),
            secondary_y=False
        )
        
        # Пики момента
        fig.add_trace(
            go.Scatter(
                x=[log['max_tq']['rpm']],
                y=[log['max_tq']['value']],
                mode='markers+text',
                marker=dict(size=10, color=log['color'], symbol='x'),
                text=[f"{log['max_tq']['value']:.1f} Nm"],
                textposition="bottom center",
                name=f"{log['name']} - Max TQ",
                showlegend=False,
                hovertemplate=(
                    f"Пик момента<br>" +
                    "RPM: %{x:.0f}<br>" +
                    "Момент: %{y:.1f} Nm<br>" +
                    "<extra></extra>"
                )
            ),
            secondary_y=True
        )
    
    # Настройка layout
    fig.update_layout(
        title="Диностенд - Мощность и Крутящий момент",
        xaxis_title="Обороты двигателя (RPM)",
        hovermode='x unified',
        height=600,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    # Настройка осей
    fig.update_yaxes(
        title_text="Мощность (HP)",
        secondary_y=False,
        gridcolor='lightgray'
    )
    
    fig.update_yaxes(
        title_text="Крутящий момент (Nm)", 
        secondary_y=True,
        gridcolor='lightgray'
    )
    
    # Отображение графика
    st.plotly_chart(fig, use_container_width=True)
    
    # Таблица с пиковыми значениями
    st.subheader("📈 Пиковые значения")
    
    peak_data = []
    for log in processed_logs:
        peak_data.append({
            'Файл': log['name'],
            'Макс. мощность (HP)': f"{log['max_hp']['value']:.1f}",
            'Обороты макс. мощности': f"{log['max_hp']['rpm']:.0f}",
            'Макс. момент (Nm)': f"{log['max_tq']['value']:.1f}",
            'Обороты макс. момента': f"{log['max_tq']['rpm']:.0f}"
        })
    
    peak_df = pd.DataFrame(peak_data)
    st.dataframe(peak_df, use_container_width=True)
    
    # Информация о параметрах
    with st.expander("ℹ️ Информация о расчетах"):
        st.markdown(f"""
        **Параметры расчета:**
        - Масса автомобиля: {car_mass} кг
        - Тип привода: {drive_type.upper()} ({drive_losses[drive_type]*100:.0f}% потерь)
        - Тип мощности: {'Crank HP (двигатель)' if power_type == 'crank' else 'WHP (колесо)'}
        - Сглаживание: окно {smooth_window} точек
        
        **Методика расчета:**
        - Мощность рассчитывается через ускорение и сопротивление
        - Потери трансмиссии учитываются для crank мощности
        - Сглаживание методом Савицкого-Голея
        - Автоматическое определение пиковых значений
        """)

if __name__ == "__main__":
    main()