# 厨艺大赛行架画面（5000 × 2800 mm）

放在大厅两根木纹柱之间的行架背景板。红金新中式风格，呼应现场的水墨山水墙和红灯笼。

| 文件 | 用途 |
| --- | --- |
| `poster-1to10-500x280mm.pdf` | **印刷用**，矢量文件，1:10 比例，喷绘时放大 10 倍 |
| `poster-print-72dpi.jpg` | **印刷用**，1:1 位图，14173 × 7937 px（72dpi） |
| `poster-preview.png` | 预览图 |
| `mockup/mockup.jpg` | 现场效果图（桌椅已移开） |
| `mockup/mockup-compare.jpg` | 现场原图和效果图左右对比 |
| `prompts.md` | 给 GPT / LibTV 用的提示词，可以自己再出几个版本 |

## 改文字

文字都在 `build_poster.py` 顶部的 `TEXT` 里（主办单位、时间、地点目前是 ××× 占位）。改完重新生成：

```bash
# 字体来自 npm（Ma Shan Zheng 毛笔楷书、思源宋体、思源黑体，均为 OFL 开源可商用）
mkdir fonts && cd fonts
for p in ma-shan-zheng noto-serif-sc noto-sans-sc; do npm pack @fontsource/$p; done
for f in *.tgz; do mkdir -p ${f%.tgz} && tar xzf $f -C ${f%.tgz}; done
cd ..
python3 build_poster.py fonts      # 生成 poster.html（字体已内嵌）
node render.mjs --print            # 需要 playwright
```

## 印刷提醒

- 主要内容离四边至少 10cm，行架扎带 / 打扣眼不会压到字。如果印刷厂要求包边或出血，请他们在四周补边。
- 下方 0.8m 左右会被比赛操作台挡住，所以标题和口号都放在画面上半部分。

## 现场效果图是怎么做的

`mockup/` 里的两个脚本，全部依据照片本身的几何：

1. `remove_furniture.py`：用 LaMa（big-lama.pt）去掉柱间的餐桌和椅子。最右侧沙发后面的蓝椅，用柱子上方的木纹顺着柱子倾斜方向往下补。
2. `compose_mockup.py`：用地砖缝拟合出地面透视（误差约 1px），补画砖缝；在柱子之间按透视贴上画面，并加上地面倒影和接触阴影。
   柱脚连线长约 9 块砖，按 600mm 砖算，柱间净宽约 5.4m、梁下约 3.0m，5m × 2.8m 行架放进去两侧各留约 20cm。**实际尺寸请到现场量一下确认。**
