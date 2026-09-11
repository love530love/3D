import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, mean_squared_error
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.preprocessing import StandardScaler
import joblib  # 用于保存模型（sklearn模型不支持save()方法）

# ---------------------- 1. 数据加载与预处理（修复重复加载、维度错误）----------------------
# 加载数据集（假设data.csv包含feature列和target列，target为分类标签）
data = pd.read_csv('data.csv')

# 处理数据维度：sklearn模型要求X为二维数组，需用data[['feature']]（双括号）
X = data[['feature']]  # 特征（二维）
y = data['target']     # 标签（一维）

# 数据预处理：特征缩放（优化模型性能）
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# 划分训练集和测试集（固定随机种子保证可复现）
X_train, X_test, y_train, y_test = train_test_split(
    X_scaled, y, test_size=0.2, random_state=42
)

# ---------------------- 2. 模型训练与优化（修复缩进、未定义变量）----------------------
# 初始化模型（可根据需求更换算法）
clf = DecisionTreeClassifier(random_state=42)

# 交叉验证评估模型
scores = cross_val_score(clf, X_train, y_train, cv=5)
print("Cross-validation scores:", scores)
print("Mean cross-validation accuracy:", scores.mean())

# 训练模型
clf.fit(X_train, y_train)

# ---------------------- 3. 模型评估（修复指标调用、结果对比错误）----------------------
# 测试集预测
y_pred = clf.predict(X_test)

# 评估指标（分类问题专用，若为回归需替换指标）
print("\nTest set evaluation:")
print("Accuracy:", accuracy_score(y_test, y_pred))
print("Precision:", precision_score(y_test, y_pred, average='weighted'))  # 多分类需指定average
print("Recall:", recall_score(y_test, y_pred, average='weighted'))
print("F1 score:", f1_score(y_test, y_pred, average='weighted'))

# 修正预测结果对比（仅对比测试集数据，避免长度不匹配）
print("\nTest set actual values:", y_test.values[:10])  # 显示前10个实际值
print("Test set predicted values:", y_pred[:10])        # 显示前10个预测值
print("Difference (abs):", np.abs(y_test.values[:10] - y_pred[:10]))

# ---------------------- 4. 错误类型判断与优化（修复缩进、定义缺失变量）----------------------
# 定义缺失变量（根据实际场景调整值）
error_type = "model"  # 可选："model"（模型问题）、"feature"（特征问题）、"data"（数据问题）
exclude_list = None   # 排除列表（若需过滤低概率数据，可传入具体数值列表）

# 缩进修复：if/elif/else后必须有缩进代码块
if error_type == "model":
    # 模型优化：更换算法或调整参数
    print("\nOptimizing model...")
    # 示例：调整决策树深度
    clf_optimized = DecisionTreeClassifier(max_depth=5, random_state=42)
    clf_optimized.fit(X_train, y_train)
    clf = clf_optimized  # 替换为优化后模型
elif error_type == "feature":
    # 特征优化：筛选有效特征
    print("\nOptimizing features...")
    selector = SelectKBest(score_func=f_classif, k=1)  # 选择1个最优特征
    X_train_selected = selector.fit_transform(X_train, y_train)
    X_test_selected = selector.transform(X_test)
    clf.fit(X_train_selected, y_train)  # 用筛选后特征重新训练
else:
    # 数据清洗：处理缺失值、异常值
    print("\nCleaning data...")
    data = data.dropna()  # 删除缺失值
    data = data[(np.abs(data['feature'] - data['feature'].mean()) < 3 * data['feature'].std())]  # 去除异常值

# 优化排除列表（若有需要）
if exclude_list is not None:
    print("\nFiltering exclude list...")
    # 筛选掉排除列表中的特征值
    mask = ~data['feature'].isin(exclude_list)
    data = data[mask]

# ---------------------- 5. 模型保存与可视化（修复保存方法、绘图变量）----------------------
# 保存模型（用joblib替换clf.save()，sklearn官方推荐）
joblib.dump(clf, 'best_model.pkl')
print("\nModel saved as 'best_model.pkl'")

# 可视化：开奖号码趋势图（用期号作为x轴，target作为y轴）
plt.figure(figsize=(10, 4))
plt.subplot(1, 2, 1)
x_trend = range(len(data))  # 期号（假设数据按时间顺序排列）
y_trend = data['target']    # 开奖号码
plt.plot(x_trend, y_trend, marker='o', markersize=2)
plt.xlabel('Period (期号)')
plt.ylabel('Target (开奖号码)')
plt.title('Target Trend (开奖号码趋势)')

# 可视化：频率分布图
plt.subplot(1, 2, 2)
plt.hist(data['target'], bins=20, edgecolor='black')
plt.xlabel('Target Value (开奖号码)')
plt.ylabel('Frequency (频率)')
plt.title('Target Frequency Distribution (开奖号码频率分布)')
plt.tight_layout()
plt.show()

# ---------------------- 6. 风险提示与反馈 ----------------------
print("\n=== Risk Notice (风险提示) ===")
print("The predicted values are not guaranteed to be accurate.")
print("This is a simulation only; actual lottery results are random and unpredictable.")
print("Please use this tool for reference only and do not rely on it for betting.")

print("\n=== Feedback (反馈) ===")
print("If you have suggestions for improvement, please let us know!")