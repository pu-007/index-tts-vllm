#!/usr/bin/env python3
import argparse
import requests
import json
import sys
from datetime import datetime
import os
import logging
import tempfile
import shutil
import subprocess
import termios
import time
import tty
import select

DEBUG = False

# 配置日志以帮助调试
logging.basicConfig(level=logging.DEBUG if DEBUG else logging.ERROR,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def getch():
    """Gets a single character from standard input."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
        if ch == '\x03':  # Handle Ctrl+C
            raise KeyboardInterrupt
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


def get_available_voices(api_url="http://localhost:8001/audio/voices"):
    """获取可用的语音角色列表"""
    try:
        logger.debug(f"获取语音角色，API地址: {api_url}")
        response = requests.get(api_url)
        response.raise_for_status()  # 检查请求是否成功
        logger.debug(f"获取语音角色响应状态码: {response.status_code}")
        voices_data = response.json()
        return list(voices_data.keys())
    except requests.exceptions.RequestException as e:
        print(f"获取语音角色失败: {str(e)}", file=sys.stderr)
        logger.error(f"获取语音角色失败: {str(e)}")
        sys.exit(1)


def read_file_content(file_path):
    """读取文件内容"""
    if not os.path.exists(file_path):
        print(f"错误: 文件 '{file_path}' 不存在", file=sys.stderr)
        sys.exit(1)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except IOError as e:
        print(f"读取文件失败: {str(e)}", file=sys.stderr)
        sys.exit(1)


def generate_default_output_filename(voice):
    """生成默认的输出文件名，格式为 speaker-角色-月日-时间.mp3"""
    now = datetime.now()
    return f"speaker-{voice}-{now.month:02d}{now.day:02d}-{now.hour:02d}{now.minute:02d}{now.second:02d}.mp3"


def play_audio_interactive(file_path):
    """使用mpv播放音频并提供交互式控制"""
    # Check if running in an interactive terminal
    if not sys.stdin.isatty():
        print("\n警告: 非交互式终端，将切换到标准播放模式。")
        print("音频将播放一次。按 Ctrl+C 停止。")
        play_audio(file_path)
        # After playback, we can't offer to save, so we just quit.
        return 'quit'

    try:
        # Check for mpv
        subprocess.run(['mpv', '--version'], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("\n错误: 本播放功能需要 'mpv'。请先安装 mpv 并确保它在您的系统 PATH 中。",
              file=sys.stderr)
        print(f"您也可以使用其他播放器手动播放文件: {file_path}")
        return 'error'

    mpv_process = None
    try:
        command = [
            'mpv', '--no-video', '--input-terminal', '--really-quiet',
            file_path
        ]
        mpv_process = subprocess.Popen(command,
                                       stdin=subprocess.PIPE,
                                       text=True,
                                       bufsize=1,
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)

        print("\n--- 交互式播放控制 (使用 mpv) ---")
        print("  [p] 暂停/播放   [q] 退出   [s] 保存")
        print("  [h] 快退 5s     [l] 快进 5s")
        print("  [j] 快退 30s    [k] 快进 30s")
        print("  [r] 从头重播")
        print("------------------------------------")
        print("mpv 将在终端中显示播放进度。")

        while mpv_process.poll() is None:
            if select.select([sys.stdin], [], [], 0.1)[0]:
                ch = getch().lower()
                if ch == 'q':
                    print("\n退出播放。")
                    mpv_process.stdin.write('quit\n')
                    mpv_process.stdin.flush()
                    break
                elif ch == 'p':
                    mpv_process.stdin.write('cycle pause\n')
                    mpv_process.stdin.flush()
                elif ch == 'r':
                    mpv_process.stdin.write('seek 0 absolute\n')
                    mpv_process.stdin.flush()
                elif ch in ('h', 'l', 'j', 'k'):
                    if ch == 'h': amount = -5
                    elif ch == 'l': amount = 5
                    elif ch == 'j': amount = -30
                    elif ch == 'k': amount = 30
                    mpv_process.stdin.write(f'seek {amount}\n')
                    mpv_process.stdin.flush()
                elif ch == 's':
                    mpv_process.stdin.write('quit\n')
                    mpv_process.stdin.flush()
                    try:
                        mpv_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        mpv_process.kill()
                    return 'save'

            time.sleep(0.05)

        # Wait for process to finish before returning
        if mpv_process.poll() is None:
            try:
                mpv_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                mpv_process.kill()

        return 'quit'

    except Exception as e:
        print(f"\n播放音频时发生未知错误: {e}", file=sys.stderr)
        return 'error'
    finally:
        if mpv_process and mpv_process.poll() is None:
            mpv_process.terminate()
            mpv_process.wait()


def play_audio(file_path):
    """使用mpv播放音频文件（非交互式）"""
    try:
        # Check for mpv
        subprocess.run(['mpv', '--version'], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("\n错误: 本播放功能需要 'mpv'。请先安装 mpv 并确保它在您的系统 PATH 中。",
              file=sys.stderr)
        print(f"您也可以使用其他播放器手动播放文件: {file_path}")
        return

    try:
        print("提示: 正在使用 mpv 播放音频... 按 Ctrl+C 退出。")
        subprocess.run(['mpv', '--no-video', file_path],
                       check=True,
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    except KeyboardInterrupt:
        print("\n播放已停止。")
    except subprocess.CalledProcessError as e:
        print(f"使用 mpv 播放音频失败: {e}", file=sys.stderr)


def text_to_speech(model,
                   voice,
                   input_text,
                   output_file,
                   api_url="http://localhost:8001/audio/speech"):
    """调用TTS API将文本转换为语音（与curl命令保持一致）"""
    # 构建请求体，与curl示例完全一致
    payload = {"model": model, "input": input_text, "voice": voice}

    try:
        logger.debug(f"发送TTS请求到: {api_url}")
        logger.debug(f"请求体: {json.dumps(payload, ensure_ascii=False)}")

        # 模拟curl的请求方式
        response = requests.post(
            api_url,
            headers={
                "Content-Type":
                "application/json",
                # 添加常见的浏览器请求头，有些服务器会检查这个
                "User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            },
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            stream=True)

        logger.debug(f"TTS响应状态码: {response.status_code}")
        logger.debug(f"响应头: {response.headers}")

        # 检查请求是否成功
        response.raise_for_status()

        # 保存响应内容到文件
        with open(output_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:  # 过滤掉保持连接的空块
                    f.write(chunk)

        print(f"语音生成成功，已保存至: {os.path.abspath(output_file)}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"语音生成失败: {str(e)}", file=sys.stderr)
        # 尝试获取服务器返回的错误信息
        if 'response' in locals():
            try:
                error_details = response.text
                print(f"服务器错误详情: {error_details}", file=sys.stderr)
                logger.error(f"服务器错误详情: {error_details}")
            except:
                pass
        logger.error(f"语音生成失败: {str(e)}")
        return False


def main():
    # 创建命令行解析器
    parser = argparse.ArgumentParser(description='TTS文本转语音命令行工具')

    # 创建子命令解析器
    subparsers = parser.add_subparsers(dest='command',
                                       required=True,
                                       help='可用命令')

    # 定义'voices'子命令 - 获取可用语音角色
    voices_parser = subparsers.add_parser('voices', help='获取所有可用的语音角色')
    voices_parser.add_argument(
        '-u',
        '--api-url',
        default="http://localhost:8001/audio/voices",
        help='获取语音角色的API地址 (默认: http://localhost:8001/audio/voices)')

    # 定义'tts'子命令 - 文本转语音
    tts_parser = subparsers.add_parser('tts', help='将文本转换为语音')
    # 位置参数：输入文本
    tts_parser.add_argument('input_text', nargs='?', help='输入文本内容')
    # 可选参数
    tts_parser.add_argument('-m',
                            '--model',
                            default='kusuriuri/IndexTTS-2-vLLM',
                            help='使用的TTS模型 (默认: kusuriuri/IndexTTS-2-vLLM)')
    tts_parser.add_argument('-v',
                            '--voice',
                            default='pu',
                            help='使用的语音角色 (默认: pu)')
    tts_parser.add_argument('--input-file', help='从文件读取输入文本')
    tts_parser.add_argument('-o',
                            '--output',
                            help='输出音频文件路径 (默认: speaker-角色-月日-时间.mp3)')
    tts_parser.add_argument(
        '-u',
        '--api-url',
        default="http://localhost:8001/audio/speech",
        help='TTS服务的API地址 (默认: http://localhost:8001/audio/speech)')
    tts_parser.add_argument('--stdin', action='store_true', help='从标准输入读取文本')
    tts_parser.add_argument('--play',
                            action='store_true',
                            help='生成语音后进入交互式播放模式 (需要安装 mpv)')

    # 解析命令行参数
    args = parser.parse_args()

    # 处理'voices'命令
    if args.command == 'voices':
        voices = get_available_voices(args.api_url)
        print("可用的语音角色:")
        for voice in voices:
            print(f"  - {voice}")
        return

    # 处理'tts'命令
    if args.command == 'tts':
        # 确定输入文本的来源
        input_text = None
        if args.input_file:
            input_text = read_file_content(args.input_file)
        elif args.input_text is not None:
            input_text = args.input_text
        elif args.stdin or not sys.stdin.isatty():
            input_text = sys.stdin.read()
        else:
            print("请输入要转换的文本（在空行处按Ctrl+D结束输入）：")
            input_text = sys.stdin.read()

        if not input_text or not input_text.strip():
            print("错误: 没有提供有效的输入文本", file=sys.stderr)
            sys.exit(1)

        # 如果设置了 --play，则使用临时文件进行交互模式
        if args.play:
            temp_output_file = None
            try:
                # 创建一个临时文件来保存音频
                with tempfile.NamedTemporaryFile(delete=False,
                                                 suffix=".mp3") as tmp_file:
                    temp_output_file = tmp_file.name

                print("正在生成语音...")
                if not text_to_speech(args.model, args.voice, input_text,
                                      temp_output_file, args.api_url):
                    return  # TTS失败，退出

                # 进入交互式播放循环
                while True:
                    action = play_audio_interactive(temp_output_file)

                    if action == 'save':
                        default_save_name = generate_default_output_filename(
                            args.voice)
                        save_path = input(
                            f"\n请输入保存路径 (默认: {default_save_name}): ").strip()
                        if not save_path:
                            save_path = default_save_name
                        try:
                            # 使用shutil.move确保文件被正确移动
                            shutil.move(temp_output_file, save_path)
                            print(f"\n音频已保存至: {os.path.abspath(save_path)}")
                            temp_output_file = None  # 标记为已移动，防止在finally中被删除
                            break  # 保存后退出循环
                        except (IOError, OSError) as e:
                            print(f"\n保存音频失败: {e}", file=sys.stderr)
                            # 让用户选择是重试保存还是继续其他操作
                            retry = input("是否重试? [Y/n]: ").lower().strip()
                            if retry == 'n':
                                break
                    elif action == 'quit':
                        print("\n已退出播放。")
                        # 只有在交互式会话中才询问是否保存
                        if sys.stdin.isatty():
                            save_on_quit = input(
                                "是否需要保存文件? [y/N]: ").lower().strip()
                            if save_on_quit == 'y':
                                default_save_name = generate_default_output_filename(
                                    args.voice)
                                save_path = input(
                                    f"\n请输入保存路径 (默认: {default_save_name}): "
                                ).strip()
                                if not save_path:
                                    save_path = default_save_name
                                try:
                                    shutil.move(temp_output_file, save_path)
                                    print(
                                        f"\n音频已保存至: {os.path.abspath(save_path)}"
                                    )
                                    temp_output_file = None
                                except (IOError, OSError) as e:
                                    print(f"\n保存音频失败: {e}", file=sys.stderr)
                        break  # 退出主循环
                    elif action == 'error':
                        # 播放器出错，直接退出
                        break
                    else:
                        # 如果play_audio_interactive返回其他任何东西，或者只是结束了，我们都退出
                        break
            finally:
                # 确保临时文件在程序退出时被删除
                if temp_output_file and os.path.exists(temp_output_file):
                    os.remove(temp_output_file)
                    logger.debug(f"临时文件 {temp_output_file} 已删除。")
        else:
            # 默认行为：直接保存
            output_file = args.output or generate_default_output_filename(
                args.voice)
            text_to_speech(args.model, args.voice, input_text, output_file,
                           args.api_url)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n程序已退出。")
        sys.exit(0)
