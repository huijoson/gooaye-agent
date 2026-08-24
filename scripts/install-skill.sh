#!/usr/bin/env bash
# ==============================================================================
# Gooaye Skill Installer Script
# ==============================================================================
# This script installs or symlinks the Gooaye Agent Skill into Antigravity
# global configuration or a specified target workspace directory.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SKILL_SOURCE_DIR="${REPO_ROOT}/.agents/skills/gooaye"

# Default destination paths
GLOBAL_GEMINI_DIR="${HOME}/.gemini/config/skills"
GLOBAL_ANTIGRAVITY_DIR="${HOME}/.gemini/antigravity-cli/skills"

print_usage() {
    echo "使用方式: $0 [選項]"
    echo ""
    echo "選項:"
    echo "  --global              (預設) 安裝/軟連結至全域 Antigravity 設定 (~/.gemini/config/skills/gooaye)"
    echo "  --target <目錄路徑>   安裝/軟連結至指定的專案工作區 (將在目標專案建立 .agents/skills/gooaye)"
    echo "  --copy                使用複製模式 (預設為建立符號連結 symlink，方便隨本專案更新同步)"
    echo "  -h, --help            顯示本說明訊息"
    echo ""
    echo "範例:"
    echo "  $0 --global"
    echo "  $0 --target /path/to/another-project"
    echo "  $0 --target /path/to/another-project --copy"
}

MODE="global"
COPY_MODE=false
TARGET_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --global)
            MODE="global"
            shift
            ;;
        --target)
            MODE="target"
            TARGET_DIR="$2"
            shift 2
            ;;
        --copy)
            COPY_MODE=true
            shift
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            echo "❌ 未知參數: $1"
            print_usage
            exit 1
            ;;
    esac
done

if [[ ! -d "${SKILL_SOURCE_DIR}" ]]; then
    echo "❌ 找不到來源技能目錄: ${SKILL_SOURCE_DIR}"
    exit 1
fi

install_skill() {
    local dest_parent="$1"
    local dest_skill_dir="${dest_parent}/gooaye"

    mkdir -p "${dest_parent}"

    if [[ -e "${dest_skill_dir}" || -L "${dest_skill_dir}" ]]; then
        echo "⚠️  目標位置已存在: ${dest_skill_dir}，正在更新..."
        rm -rf "${dest_skill_dir}"
    fi

    if [[ "${COPY_MODE}" == true ]]; then
        cp -R "${SKILL_SOURCE_DIR}" "${dest_skill_dir}"
        echo "✅ 已複製 Gooaye 技能至: ${dest_skill_dir}"
    else
        ln -s "${SKILL_SOURCE_DIR}" "${dest_skill_dir}"
        echo "✅ 已建立符號連結 (Symlink): ${dest_skill_dir} -> ${SKILL_SOURCE_DIR}"
    fi
}

echo "=========================================="
echo "🚀 Gooaye (股癌) 知識庫技能安裝程式"
echo "=========================================="

if [[ "${MODE}" == "global" ]]; then
    echo "📦 安裝模式: 全域安裝 (Global)"
    install_skill "${GLOBAL_GEMINI_DIR}"
    # 若 antigravity-cli 目錄存在，亦一併建立連結以確保完全相容
    if [[ -d "${HOME}/.gemini/antigravity-cli" ]]; then
        mkdir -p "${GLOBAL_ANTIGRAVITY_DIR}"
        if [[ ! -e "${GLOBAL_ANTIGRAVITY_DIR}/gooaye" && ! -L "${GLOBAL_ANTIGRAVITY_DIR}/gooaye" ]]; then
            ln -s "${SKILL_SOURCE_DIR}" "${GLOBAL_ANTIGRAVITY_DIR}/gooaye"
            echo "🔗 同步連結至: ${GLOBAL_ANTIGRAVITY_DIR}/gooaye"
        fi
    fi
    echo ""
    echo "🎉 安裝完成！現在您可以在任何 Antigravity 工作區中向 Agent 提問股癌觀點與心態健檢。"
elif [[ "${MODE}" == "target" ]]; then
    if [[ -z "${TARGET_DIR}" ]]; then
        echo "❌ 請指定目標專案目錄: --target <路徑>"
        exit 1
    fi
    TARGET_WORKSPACE="$(cd "${TARGET_DIR}" && pwd)"
    echo "📦 安裝模式: 目標專案安裝 -> ${TARGET_WORKSPACE}"
    install_skill "${TARGET_WORKSPACE}/.agents/skills"
    echo ""
    echo "🎉 安裝完成！已將 Gooaye 技能配置於目標專案: ${TARGET_WORKSPACE}/.agents/skills/gooaye"
fi

echo "=========================================="
