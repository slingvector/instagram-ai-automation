import os
import sys
import time
import sqlite3
import curses
import subprocess
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

class Dashboard:
    def __init__(self):
        self.db_path = os.path.abspath("data/bulk_post_state.db")
        self.log_file = os.path.abspath("logs/unified_industrial.log")
        self.states = [
            ("SCANNED", "🔍"),
            ("DISCOVERED", "🎯"),
            ("DOWNLOADED", "💾"),
            ("CAPTIONED", "📝"),
            ("JOB_CREATED", "🏗️"),
            ("MEDIA_PROCESSED", "🎬"),
            ("POSTING", "📡"),
            ("POSTED", "🚀"),
            ("FAILED", "❌")
        ]

    def get_stats(self):
        if not os.path.exists(self.db_path):
            return None, None
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT state, COUNT(*) FROM reel_states GROUP BY state")
            rows = cursor.fetchall()
            stats = {row[0]: row[1] for row in rows}
            cursor.execute("SELECT error_message FROM reel_states WHERE state = 'FAILED' ORDER BY updated_at DESC LIMIT 5")
            failures = [f[0] for f in cursor.fetchall()]
            return stats, failures
        finally:
            conn.close()

    def run_command(self, cmd):
        try:
            subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except:
            return False

    def safe_addstr(self, stdscr, y, x, string, attr=0):
        """Safely write to curses, handling terminal boundaries and errors."""
        try:
            h, w = stdscr.getmaxyx()
            if y < h and x < w:
                # Truncate string to avoid wrapping/error at edge
                max_len = w - x - 1
                stdscr.addstr(y, x, string[:max_len], attr)
        except:
            pass

    def draw(self, stdscr):
        curses.curs_set(0)
        stdscr.nodelay(1)
        stdscr.timeout(1000) # Refresh every second

        while True:
            stdscr.clear()
            h, w = stdscr.getmaxyx()
            
            if h < 20 or w < 60:
                stdscr.addstr(0, 0, "⚠️ Terminal too small! Please resize.")
                stdscr.refresh()
                time.sleep(1)
                continue

            # Header
            stdscr.attron(curses.A_BOLD | curses.color_pair(1))
            header = "═══ 📟 MCR INDUSTRIAL COMMAND CENTER v2.1 ═══"
            self.safe_addstr(stdscr, 0, (w - len(header)) // 2, header, curses.A_BOLD | curses.color_pair(1))
            stdscr.attroff(curses.A_BOLD | curses.color_pair(1))
            
            sub_header = f"🕒 System Time: {datetime.now().strftime('%H:%M:%S')} | Target: 100 Reels"
            self.safe_addstr(stdscr, 1, (w - len(sub_header)) // 2, sub_header)
            
            stats, failures = self.get_stats()
            if not stats:
                empty_msg = "🟡 Searching for State DB... (Ensure bulk_post.py is initialized)"
                self.safe_addstr(stdscr, 5, (w - len(empty_msg)) // 2, empty_msg)
            else:
                total = sum(stats.values())
                self.safe_addstr(stdscr, 3, 2, f"📊 Pipeline Saturation: {total}/25")
                
                # Draw Progress Bars
                for i, (state_name, icon) in enumerate(self.states):
                    count = stats.get(state_name, 0)
                    perc = (count / total * 100) if total > 0 else 0
                    bar_len = min(int((perc / 100) * (w - 30)), w - 30)
                    bar = "█" * bar_len
                    
                    color = 2 if state_name == "POSTED" else (3 if state_name == "FAILED" else 4)
                    text = f"{icon} {state_name:<16} | {count:>3} | {bar}"
                    self.safe_addstr(stdscr, 5 + i, 2, text, curses.color_pair(color))

                # Failure Audit
                if failures:
                    self.safe_addstr(stdscr, 15, 2, "🛑 ERROR TELEMETRY (Recent):", curses.A_BOLD | curses.color_pair(3))
                    for i, f in enumerate(failures):
                        if 16 + i < h - 5:
                            self.safe_addstr(stdscr, 16 + i, 4, f"• {f}")

            # Footer / Action Menu
            menu_y = h - 3
            band = " ACTIONS "
            stdscr.attron(curses.A_REVERSE)
            self.safe_addstr(stdscr, menu_y, (w - len(band)) // 2, band)
            stdscr.attroff(curses.A_REVERSE)
            
            actions = "[P] Park | [R] Retry | [S] Start 100 | [L] Log Peek | [Q] Quit"
            self.safe_addstr(stdscr, menu_y + 1, (w - len(actions)) // 2, actions)

            # Input Handling
            key = stdscr.getch()
            if key in [ord('q'), ord('Q')]:
                break
            elif key in [ord('p'), ord('P')]:
                self.run_command("./park_pipeline.sh")
                self.safe_addstr(stdscr, menu_y + 2, (w - 25) // 2, "⚠️ Parking Signal Sent...", curses.color_pair(3))
            elif key in [ord('r'), ord('R')]:
                self.run_command("python3 tests/bulk_post.py --retry-failed")
                self.safe_addstr(stdscr, menu_y + 2, (w - 25) // 2, "🔄 Retry Signal Sent...", curses.color_pair(2))
            elif key in [ord('s'), ord('S')]:
                self.run_command("python3 tests/bulk_post.py --count 25")
                self.safe_addstr(stdscr, 20, (w - 30) // 2, "🚀 Starting 25-Reel Batch...", curses.color_pair(2))
            elif key in [ord('l'), ord('L')]:
                # Log Peek Overlay
                stdscr.clear()
                self.safe_addstr(stdscr, 0, 0, "═══ 🔍 LOG PEEK (Last 20 Lines) ═══", curses.A_BOLD | curses.color_pair(1))
                if os.path.exists(self.log_file):
                    with open(self.log_file, "r") as f:
                        lines = f.readlines()[-20:]
                        for idx, line in enumerate(lines):
                            self.safe_addstr(stdscr, idx + 2, 0, line.strip())
                else:
                    self.safe_addstr(stdscr, 2, 0, "❌ Log file not found yet.")
                    
                self.safe_addstr(stdscr, h-1, 0, "Press any key to return...", curses.A_REVERSE)
                stdscr.refresh()
                stdscr.nodelay(0)
                stdscr.getch()
                stdscr.nodelay(1)

            stdscr.refresh()

def main():
    dashboard = Dashboard()
    os.environ.setdefault('ESCDELAY', '25')
    
    def run_curses(stdscr):
        curses.start_color()
        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK) # Header
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK) # Success
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)   # Failure
        curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLACK) # Normal
        dashboard.draw(stdscr)

    curses.wrapper(run_curses)

if __name__ == "__main__":
    main()
