"""用 LaMa（big-lama.pt）把柱子之间的餐桌椅从现场照片里移走。

    python remove_furniture.py <现场照片> <big-lama.pt> <输出 png>

遮罩是手工标的多边形（原图 2016×1512 像素坐标）。
"""
import sys

import cv2
import numpy as np
import torch

# 要移走的桌椅
FURNITURE = [
    # 左侧灰椅（压在沙发前面）
    [(436, 748), (470, 744), (505, 748), (530, 770), (552, 800), (560, 838), (600, 842), (616, 858),
     (616, 892), (612, 978), (592, 984), (585, 915), (570, 918), (568, 930), (555, 930), (552, 912),
     (508, 915), (503, 1014), (476, 1014), (470, 900), (440, 858)],
    # 中间餐桌：桌面、花瓶、桌腿和底盘
    [(598, 792), (720, 770), (722, 695), (792, 695), (795, 762), (905, 766), (908, 812), (600, 812)],
    [(768, 716), (842, 716), (842, 790), (768, 790)],
    [(670, 950), (865, 950), (865, 1004), (670, 1004)],
    [(684, 810), (705, 810), (705, 935), (684, 935)],
    # 中间餐桌前的蓝椅
    [(700, 778), (850, 778), (858, 880), (852, 940), (860, 1030), (840, 1038), (820, 960), (735, 960),
     (718, 1035), (695, 1032), (705, 940), (698, 880)],
    # 中间餐桌后的灰椅
    [(905, 770), (1000, 768), (1035, 762), (1078, 762), (1080, 800), (1075, 905), (1060, 905),
     (1050, 930), (935, 930), (932, 1004), (912, 1004), (908, 900)],
    # 中间偏右的蓝椅
    [(920, 795), (1030, 795), (1040, 830), (1048, 900), (1145, 905), (1155, 935), (1152, 985),
     (1147, 1090), (1130, 1092), (1125, 1000), (1060, 1010), (1054, 1138), (1034, 1138), (1030, 1010),
     (955, 1010), (950, 1102), (928, 1102), (926, 950)],
    # 右侧餐桌：桌面和摆件、桌腿、底盘
    [(1088, 822), (1200, 815), (1215, 775), (1280, 770), (1290, 745), (1345, 745), (1345, 812),
     (1392, 812), (1538, 870), (1532, 892), (1200, 899), (1088, 837)],
    [(1245, 880), (1345, 880), (1345, 1048), (1458, 1104), (1442, 1127), (1225, 1127), (1158, 1066),
     (1245, 1050)],
    # 右侧餐桌后的灰椅
    [(1122, 770), (1180, 764), (1245, 775), (1250, 880), (1245, 992), (1225, 992), (1222, 935),
     (1150, 935), (1145, 1002), (1125, 1002), (1125, 900)],
    # 右侧餐桌前的灰椅
    [(1290, 1020), (1350, 995), (1395, 935), (1410, 905), (1460, 892), (1556, 892), (1564, 920),
     (1542, 1030), (1532, 1080), (1537, 1227), (1515, 1230), (1500, 1100), (1420, 1110), (1420, 1258),
     (1394, 1260), (1390, 1110), (1310, 1080), (1306, 1197), (1281, 1197), (1285, 1060)],
]

# 行架前方整片地面：桌椅的影子都在这里，整片重画地砖
FLOOR = [(440, 850), (560, 850), (1590, 995), (1602, 1070), (1562, 1240), (1430, 1278), (1280, 1225),
         (1050, 1155), (900, 1125), (680, 1055), (470, 1035), (430, 960)]

# 最右边沙发后面的蓝椅：先框一个大范围，再扣掉挡在前面的沙发
FAR_RIGHT_CHAIR = [(1588, 788), (1846, 788), (1846, 1062), (1588, 1062)]
RIGHT_SOFA = [(1690, 1300), (1690, 940), (1722, 925), (1722, 845), (1735, 822), (1760, 815),
              (1800, 816), (1822, 832), (1830, 860), (1832, 885), (1850, 878), (1882, 898),
              (2016, 880), (2016, 1300)]
# 沙发靠垫和沙发座：蓝色识别不碰这里
CUSHIONS = [(1722, 985), (1722, 893), (1735, 886), (1752, 884), (1755, 840), (1762, 825), (1775, 818),
            (1800, 818), (1818, 830), (1826, 860), (1850, 874), (1890, 900), (1890, 1300), (1690, 1300),
            (1690, 962), (1705, 950), (1722, 945)]

# 右柱左边缘 (1603,1007)->(1640,500)，每往上 1px 向右偏 0.073px；柱脚沿 y=1007+0.11(x-1603)
PILLAR_LEAN, PILLAR_X, PILLAR_FOOT_Y, PILLAR_FOOT_SLOPE = 0.073, 1603, 1007, 0.11


def teal_pixels(bgr):
    """蓝绿色椅面（和墨绿沙发的色相能分开）。"""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return ((h >= 80) & (h <= 108) & (s > 22) & (v < 140)).astype(np.uint8) * 255


def build_mask(shape, bgr):
    mask = np.zeros(shape[:2], np.uint8)
    for poly in FURNITURE:
        cv2.fillPoly(mask, [np.array(poly, np.int32)], 255)
    mask = cv2.dilate(mask, np.ones((15, 15), np.uint8))
    # 椅子在地上的影子往下多盖一点
    mask = cv2.dilate(mask, np.ones((25, 3), np.uint8), anchor=(1, 0))
    cv2.fillPoly(mask, [np.array(FLOOR, np.int32)], 255)

    far = np.zeros_like(mask)
    cv2.fillPoly(far, [np.array(FAR_RIGHT_CHAIR, np.int32)], 255)
    sofa = np.zeros_like(mask)
    cv2.fillPoly(sofa, [np.array(RIGHT_SOFA, np.int32)], 255)
    keep = np.zeros_like(mask)
    cv2.fillPoly(keep, [np.array(CUSHIONS, np.int32)], 255)
    teal = teal_pixels(bgr) & far & ~keep
    far[sofa > 0] = 0
    far |= cv2.dilate(teal, np.ones((3, 3), np.uint8)) & ~keep
    return mask | far, far


def inpaint(model, rgb, mask):
    h, w = mask.shape
    ph, pw = (8 - h % 8) % 8, (8 - w % 8) % 8
    img = np.pad(rgb, ((0, ph), (0, pw), (0, 0)), mode="reflect")
    m = np.pad(mask, ((0, ph), (0, pw)), mode="reflect")
    img_t = torch.from_numpy(img).permute(2, 0, 1)[None].float() / 255
    m_t = (torch.from_numpy(m)[None, None] > 127).float()
    with torch.no_grad():
        out = model(img_t, m_t)[0].permute(1, 2, 0).numpy()
    out = np.clip(out * 255, 0, 255).astype(np.uint8)[:h, :w]
    keep = (mask == 0)[..., None]
    return np.where(keep, rgb, out)


def patch_pillar(result, original, far):
    """LaMa 在柱子前会把椅子"补"回来，这里改用柱子上方的木纹顺着柱子倾斜往下贴。"""
    h, w = far.shape
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    edge_x = PILLAR_X + (PILLAR_FOOT_Y - ys) * PILLAR_LEAN
    foot_y = PILLAR_FOOT_Y + (xs - PILLAR_X) * PILLAR_FOOT_SLOPE
    # 顶部多往上 20px 渐变过渡，避免木纹出现横向接缝
    hull_top = FAR_RIGHT_CHAIR[0][1]
    ramp = np.clip((ys - (hull_top - 20)) / 30, 0, 1)
    zone = (far > 0) | ((ys >= hull_top - 20) & (ys < hull_top + 10) & (xs > FAR_RIGHT_CHAIR[0][0])
                        & (xs < FAR_RIGHT_CHAIR[1][0]))
    region = (zone & (xs >= edge_x) & (ys < foot_y)).astype(np.float32) * ramp
    shift = 280
    src = cv2.remap(original, xs + shift * PILLAR_LEAN, ys - shift, cv2.INTER_LINEAR).astype(np.float32)
    # 柱子下部比上部略暗，按交界处的亮度比例校正
    below = original[760:785, 1645:1700].reshape(-1, 3).mean(0)
    above = original[760 - shift:785 - shift, 1665:1720].reshape(-1, 3).mean(0)
    src *= below / above
    a = cv2.GaussianBlur(region, (0, 0), 1.2)[..., None]
    return np.clip(result * (1 - a) + src * a, 0, 255).astype(np.uint8)


def main(photo, weights, out_path):
    bgr = cv2.imread(photo)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    mask, far = build_mask(rgb.shape, bgr)
    cv2.imwrite(out_path.replace(".png", "-mask.png"), mask)
    model = torch.jit.load(weights, map_location="cpu").eval()
    result = patch_pillar(inpaint(model, rgb, mask), rgb, far)
    cv2.imwrite(out_path, cv2.cvtColor(result, cv2.COLOR_RGB2BGR))
    print("wrote", out_path)


if __name__ == "__main__":
    main(*sys.argv[1:4])
