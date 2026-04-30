@echo off
REM 鍋忓ソ鏁版嵁鐢熸垚鑴氭湰

echo ========================================
echo   DPO Preference Data Generator
echo ========================================
echo.

set PROVIDER=lmstudio
set NUM_SAMPLES=10
set OUTPUT=data\synthetic_dpo.jsonl

REM 鍙互淇敼浠ヤ笅鍙傛暟
REM PROVIDER: lmstudio / ollama / openai / claude
REM NUM_SAMPLES: 鐢熸垚鏁伴噺
REM OUTPUT: 杈撳嚭鏂囦欢璺緞

python generate_preference_data.py ^
    --provider %PROVIDER% ^
    --num_samples %NUM_SAMPLES% ^
    --output %OUTPUT%

echo.
echo 瀹屾垚锛佹暟鎹繚瀛樺湪 %OUTPUT%
pause
