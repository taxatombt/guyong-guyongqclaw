@echo off
REM MiniMind DPO 璁粌蹇€熷惎鍔ㄨ剼鏈?REM 涓嶄慨鏀?minimind_study 婧愮爜锛岀嫭绔嬭繍琛?
echo ========================================
echo   MiniMind DPO Training - Quick Start
echo ========================================
echo.

REM 妫€鏌?Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 鏈畨瑁?    pause
    exit /b 1
)

REM 瀹夎渚濊禆
echo [1/3] 瀹夎渚濊禆...
pip install -q torch transformers datasets tqdm numpy openai anthropic requests
if errorlevel 1 (
    echo [WARNING] 閮ㄥ垎渚濊禆瀹夎澶辫触锛岀户缁?..
)

REM 妫€鏌ユ暟鎹?if not exist "data\dpo_example.jsonl" (
    echo [WARNING] 鏁版嵁鏂囦欢涓嶅瓨鍦紝浣跨敤榛樿绀轰緥鏁版嵁
)

REM 璁粌鍙傛暟
set DATA_PATH=data\dpo_example.jsonl
set FROM_WEIGHT=jingyaogong/minimind-3B
set SAVE_DIR=out
set EPOCHS=1
set BATCH_SIZE=2
set LR=4e-8
set BETA=0.15

echo.
echo [2/3] 璁粌閰嶇疆锛?echo   鏁版嵁: %DATA_PATH%
echo   妯″瀷: %FROM_WEIGHT%
echo   杞暟: %EPOCHS%
echo   Batch: %BATCH_SIZE%
echo   瀛︿範鐜? %LR%
echo   Beta: %BETA%
echo.

REM 妫€鏌?CUDA
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"

echo [3/3] 寮€濮嬭缁?..
python train_dpo.py ^
    --data_path %DATA_PATH% ^
    --from_weight %FROM_WEIGHT% ^
    --save_dir %SAVE_DIR% ^
    --epochs %EPOCHS% ^
    --batch_size %BATCH_SIZE% ^
    --learning_rate %LR% ^
    --beta %BETA%

echo.
echo ========================================
echo   璁粌瀹屾垚锛佹ā鍨嬩繚瀛樺湪 out/ 鐩綍
echo ========================================
pause
