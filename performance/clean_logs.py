"""
清理所有测试日志文件
"""
import os
import glob

def clean_test_logs():
    """清理所有测试日志文件"""
    results_dir = os.path.join(os.path.dirname(__file__), "results")
    
    if not os.path.exists(results_dir):
        print(f"Results directory not found: {results_dir}")
        return
    
    # 清理logs目录
    logs_dir = os.path.join(results_dir, "logs")
    if os.path.exists(logs_dir):
        log_files = glob.glob(os.path.join(logs_dir, "**", "*.log"), recursive=True)
        for log_file in log_files:
            try:
                os.remove(log_file)
                print(f"Deleted: {log_file}")
            except Exception as e:
                print(f"Error deleting {log_file}: {e}")
        print(f"Cleaned {len(log_files)} log files")
    
    # 清理csv目录
    csv_dir = os.path.join(results_dir, "csv")
    if os.path.exists(csv_dir):
        csv_files = glob.glob(os.path.join(csv_dir, "*.csv"))
        for csv_file in csv_files:
            try:
                os.remove(csv_file)
                print(f"Deleted: {csv_file}")
            except Exception as e:
                print(f"Error deleting {csv_file}: {e}")
        print(f"Cleaned {len(csv_files)} CSV files")
    
    # 清理json目录
    json_dir = os.path.join(results_dir, "json")
    if os.path.exists(json_dir):
        json_files = glob.glob(os.path.join(json_dir, "*.json"))
        for json_file in json_files:
            try:
                os.remove(json_file)
                print(f"Deleted: {json_file}")
            except Exception as e:
                print(f"Error deleting {json_file}: {e}")
        print(f"Cleaned {len(json_files)} JSON files")
    
    print("\nAll test logs cleaned successfully!")

if __name__ == "__main__":
    clean_test_logs()

