@echo off

IF "%1"=="install" GOTO install
IF "%1"=="init-db" GOTO init-db
IF "%1"=="migrate" GOTO migrate
IF "%1"=="backend" GOTO backend
IF "%1"=="frontend" GOTO frontend
IF "%1"=="conda-env" GOTO condaenv
IF "%1"=="help" GOTO help
GOTO help

:migrate
echo Running database migrations...
cd backend
set FLASK_APP=run.py
flask db upgrade
GOTO end

:install
echo Installing backend dependencies...
cd backend && pip install -r requirements.txt
echo Installing frontend dependencies...
cd ..\frontend && npm install
GOTO end

:init-db
echo Applying database migrations...
cd backend
set FLASK_APP=run.py
flask db upgrade
cd ..
GOTO end

:backend
echo Starting backend server...
cd backend && python run.py
GOTO end

:frontend
echo Starting frontend development server...
cd frontend && npm start
GOTO end

:condaenv
echo Creating Conda environment...
call conda create -n detector python=3.10 -y
call conda activate detector
echo Conda environment 'detector' created and activated
echo Installing PyTorch with CUDA support...
call conda install pytorch torchvision torchaudio pytorch-cuda=11.8 -c pytorch -c nvidia -y
GOTO end

:help
echo Available commands:
echo   run.bat conda-env    - Create Conda environment with PyTorch
echo   run.bat install      - Install all dependencies
echo   run.bat init-db      - Initialize the database
echo   run.bat backend      - Run backend development server
echo   run.bat frontend     - Run frontend development server
GOTO end

:end 