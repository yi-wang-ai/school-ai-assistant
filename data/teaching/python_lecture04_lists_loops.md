> 【虚构示例】本讲义为作品集演示而编写，不代表任何真实课程。

# 《Python 程序设计基础》第 4 讲：列表与循环

- 课程代码：CS101
- 适用专业：大数据技术、人工智能技术应用（一年级）
- 学时：4 学时（理论 2 + 实验 2）

## 4.1 学习目标

1. 能创建列表，并用下标访问、修改元素。
2. 能使用 `for` 循环遍历列表，使用 `range()` 生成整数序列。
3. 能使用 `while` 循环处理"条件满足前一直重复"的问题。
4. 能用 `break` 和 `continue` 控制循环。
5. 能写出简单的列表推导式。

## 4.2 列表

列表是有序、可修改的元素集合，用方括号表示：

```python
scores = [86, 92, 78, 95]
print(scores[0])    # 86，下标从 0 开始
print(scores[-1])   # 95，负下标从末尾数
scores[2] = 80      # 修改第三个元素
scores.append(88)   # 在末尾添加
print(len(scores))  # 5
```

常见错误：访问 `scores[5]` 会引发 `IndexError`，因为长度为 5 的列表最大下标是 4。

切片 `scores[1:3]` 返回下标 1 和 2 的元素，不包含 3。

## 4.3 for 循环与 range()

```python
for s in scores:
    print(s)

for i in range(len(scores)):
    print(i, scores[i])
```

`range(n)` 生成 0 到 n-1；`range(a, b)` 生成 a 到 b-1；`range(a, b, step)` 按步长生成。

例：计算平均分

```python
total = 0
for s in scores:
    total += s
average = total / len(scores)
```

也可以直接用内置函数：`sum(scores) / len(scores)`。

## 4.4 while 循环

`while` 在条件为真时重复执行，适合事先不知道循环次数的情况。

```python
balance = 1000
years = 0
while balance < 2000:
    balance *= 1.05
    years += 1
print(years)   # 15
```

常见错误：忘记在循环体内改变条件（例如漏写 `years += 1` 不影响结束，但漏写 `balance *= 1.05` 会造成死循环）。

## 4.5 break 与 continue

- `break`：立即结束整个循环。
- `continue`：跳过本次循环剩余部分，进入下一次。

```python
for s in scores:
    if s < 60:
        print("有不及格")
        break
```

## 4.6 列表推导式

```python
squares = [x * x for x in range(1, 6)]          # [1, 4, 9, 16, 25]
passed = [s for s in scores if s >= 60]         # 筛选及格成绩
```

列表推导式适合"由一个列表生成另一个列表"的简单情况；逻辑复杂时用普通 for 循环更清晰。

## 4.7 实验任务（2 学时）

1. 输入 10 名学生的成绩，输出最高分、最低分和平均分（不使用 `max`/`min`）。
2. 用 `while` 循环计算：每年存入 1000 元，年利率 3%，多少年后本息超过 10000 元。
3. 用列表推导式从成绩列表中筛选出 90 分及以上的成绩。

## 4.8 课后思考

- `for` 和 `while` 分别适合什么场景？
- 为什么修改正在遍历的列表（如在 for 循环中 `remove` 元素）可能出错？
