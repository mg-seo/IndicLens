from __future__ import annotations

import streamlit as st

from ui.sidebar import sidebar_inputs
import views.backtest_view as bt_v
import views.correlation_view as corr_v
import views.data_preview as dp


st.set_page_config(page_title="IndicLens", layout="wide")

st.title("📈 IndicLens — 초보 트레이더용 백테스트 & 상관분석")
st.caption("Binance 데이터 기반")

# 사이드바 입력
inputs = sidebar_inputs()

# 탭 구성
_tab1, _tab2, _tab3= st.tabs(["🧪 백테스트", "🔗 상관분석", "데이터"])

with _tab1:
    bt_v.view(inputs)

with _tab2:
    corr_v.view(inputs)

with _tab3:
    dp.view(inputs.symbol, inputs.interval)

with st.expander("ℹ️ 사용 팁"):
    st.markdown(
        """
        - **룩어헤드 방지**: 시그널은 다음 캔들 시가에 체결되도록 처리되어 있습니다.
        - **수수료/슬리피지**: 수수료 프리셋 — 테이커 0.04%, 메이커 0.02%. 슬리피지는 % 단위(기본 0.50%, 0.25% 단위)로 입력합니다.
        - **파생데이터 30일 제한**: 바이낸스 공개 히스토리 API 특성상 최근 30일만 제공합니다.
        """
    )
