param(
    [Parameter(Position=0)]
    [string]$Command
)

function CheckAndInstallNode {
    # 检查是否安装了 Node.js
    $nodeInstalled = $null
    try {
        $nodeInstalled = Get-Command node -ErrorAction Stop
    } catch {
        Write-Host "Node.js not found. Installing Node.js..."
        
        # 检查是否安装了 winget
        $wingetInstalled = $null
        try {
            $wingetInstalled = Get-Command winget -ErrorAction Stop
            # 使用 winget 安装 Node.js
            winget install OpenJS.NodeJS
        } catch {
            # 如果没有 winget，提供下载链接
            Write-Host "Please install Node.js from: https://nodejs.org/dist/v18.18.0/node-v18.18.0-x64.msi"
            Write-Host "After installation, please restart PowerShell and run this script again."
            exit 1
        }
    }
    
    # 验证安装
    try {
        $nodeVersion = node -v
        $npmVersion = npm -v
        Write-Host "Node.js version: $nodeVersion"
        Write-Host "npm version: $npmVersion"
    } catch {
        Write-Host "Node.js installation failed. Please install manually from https://nodejs.org/"
        exit 1
    }
}

function Install {
    Write-Host "Checking Node.js installation..."
    CheckAndInstallNode
    
    Write-Host "Installing backend dependencies..."
    #Set-Location backend
    pip install -r requirements.txt
    #Set-Location ..
    
    Write-Host "Installing frontend dependencies..."
    Set-Location frontend
    npm install
    Set-Location ..
}

function InitDb {
    Write-Host "Applying database migrations..."
    Set-Location backend
    $env:FLASK_APP = "run.py"
    flask db upgrade
    Set-Location ..
}

function StartBackend {
    Write-Host "Starting backend server..."
    Set-Location backend
    python run.py
    Set-Location ..
}

function StartFrontend {
    Write-Host "Starting frontend development server..."
    Set-Location frontend
    npm start
    Set-Location ..
}

function CreateCondaEnv {
    Write-Host "Creating Conda environment..."
    conda create -n detector python=3.10 -y
    conda activate detector
    Write-Host "Installing PyTorch with CUDA support..."
    conda install pytorch torchvision torchaudio pytorch-cuda=11.8 -c pytorch -c nvidia -y
    Write-Host "Conda environment 'detector' created and activated"
}

function ShowHelp {
    Write-Host "Available commands:"
    Write-Host "  .\run.ps1 conda-env    - Create Conda environment with PyTorch"
    Write-Host "  .\run.ps1 install      - Install all dependencies"
    Write-Host "  .\run.ps1 init-db      - Initialize the database"
    Write-Host "  .\run.ps1 backend      - Run backend development server"
    Write-Host "  .\run.ps1 frontend     - Run frontend development server"
}

function RunMigrations {
    Write-Host "Running database migrations..."
    Set-Location backend
    $env:FLASK_APP = "run.py"
    flask db upgrade
    Set-Location ..
}

switch ($Command) {
    "install" { Install }
    "init-db" { InitDb }
    "migrate" { RunMigrations }
    "backend" { StartBackend }
    "frontend" { StartFrontend }
    "conda-env" { CreateCondaEnv }
    default { ShowHelp }
} 