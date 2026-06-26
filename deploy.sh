#!/bin/bash
# DBAgent 快速启动脚本
# 用法: bash deploy.sh

set -e

echo "========================================="
echo "  DBAgent 部署脚本"
echo "========================================="

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ 未安装 Docker，请先安装：https://docs.docker.com/get-docker/"
    exit 1
fi

# 检查 .env
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "📝 未找到 .env，从 .env.example 复制..."
        cp .env.example .env
        echo "⚠️  请编辑 .env 填入真实的 API Key："
        echo "   DEEPSEEK_API_KEY=sk-xxx"
        echo "   ONEDBA_ACCESS_TOKEN=xxx"
        echo ""
        read -p "编辑完成后按回车继续..."
    else
        echo "❌ 缺少 .env.example 文件"
        exit 1
    fi
fi

# 检查 .env 是否已填写真实值
if grep -q "your_deepseek_api_key" .env; then
    echo "⚠️  检测到 .env 中 API Key 未填写，请编辑 .env 后重试"
    exit 1
fi

echo "✅ 环境检查通过"
echo ""

# 启动
echo "🚀 构建并启动服务..."
docker-compose up -d --build

echo ""
echo "========================================="
echo "  部署完成！"
echo "  访问地址: http://localhost:8000"
echo "  查看日志: docker-compose logs -f"
echo "  停止服务: docker-compose down"
echo "========================================="