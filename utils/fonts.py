# utils/fonts.py
import os
import matplotlib
from matplotlib import font_manager as fm

def setup_korean_font(local_font_path: str | None = None) -> str:
    """
    1) local_font_path가 있으면 해당 폰트를 등록 후 그 '실제 패밀리명'으로 rcParams 설정
    2) 없으면 Windows의 'Malgun Gothic' 시도
    3) 실패 시 마지막으로 DejaVu + minus 설정만

    반환: 적용된 폰트 패밀리명(또는 빈 문자열)
    """
    matplotlib.rcParams["axes.unicode_minus"] = False

    # 1) 동봉 폰트 우선
    if local_font_path and os.path.exists(local_font_path):
        try:
            fm.fontManager.addfont(local_font_path)
            family = fm.FontProperties(fname=local_font_path).get_name()
            matplotlib.rcParams["font.family"] = family
            return family
        except Exception as e:
            print(f"[setup_korean_font] addfont 실패: {e}")

    # 2) Windows 시스템 'Malgun Gothic' 시도
    try:
        # fallback_to_default=False: 없으면 예외
        _ = fm.findfont("Malgun Gothic", fallback_to_default=False)
        matplotlib.rcParams["font.family"] = "Malgun Gothic"
        return "Malgun Gothic"
    except Exception:
        pass

    # 3) 마지막: 기본 폰트 유지(한글은 □ 로 나올 수 있음)
    # 그래도 minus 깨짐은 방지됨
    return ""
