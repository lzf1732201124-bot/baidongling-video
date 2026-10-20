"""把行架画面合成进现场照片（桌椅已用 remove_furniture.py 移走）。

    python compose_mockup.py <venue.jpg> <cleared.png> <cleared-mask.png> <poster.png> <输出.jpg>

几何全部来自照片本身：
- 地砖缝两组直线拟合出地面单应矩阵 FLOOR_H（地砖格 -> 像素，误差约 1px），
  用来在去掉桌椅的区域补画砖缝；
- 两柱之间的开口 = 左柱右边缘、右柱左边缘、柱脚连线、横梁线围成的四边形，
  上下两条边交于地平线上的同一个消失点 (-1663, 552)，透视自洽；
- 柱脚连线长 8.96 块砖，按 600mm 砖算开口约 5.37m 宽、梁下约 3.0m 高，
  5m×2.8m 行架居中放进去，两侧各留约 18cm，顶部离梁约 20cm。
"""
import sys

import cv2
import numpy as np

FLOOR_H = np.array([
    [1.04069659e+02, -2.11942168e+02, 3.31685821e+02],
    [-3.46212185e+01, -7.29311800e+01, 1.06896590e+03],
    [-6.41525042e-02, -1.19318828e-01, 1.00000000e+00],
])

# 两柱之间的开口（像素）：左下、右下、右上、左上
GAP = np.float32([(560, 858), (1596, 1000), (1658, 180), (546, 305)])
GAP_W, GAP_H = 5.37, 3.0          # 开口的实际尺寸（米），由地砖格数推得
TRUSS_W, TRUSS_H = 5.0, 2.8
FRAME = 0.012                      # 行架方管露出的边框宽（米）

# 左边沙发的右端挡在行架左下角前面
LEFT_SOFA = [(540, 700), (562, 705), (568, 722), (568, 752), (582, 752), (582, 948), (540, 948)]
# 只在这片区域里补画地砖缝（沙发、墙面不画）
FLOOR_ZONE = [(0, 950), (578, 950), (578, 862), (1596, 1001), (1700, 1016), (1700, 1512), (0, 1512)]


def gap_homography():
    """开口平面坐标（米，原点在左下，向上为正）-> 像素。"""
    src = np.float32([(0, 0), (GAP_W, 0), (GAP_W, GAP_H), (0, GAP_H)])
    return cv2.getPerspectiveTransform(src, GAP)


def to_pixels(Hp, pts):
    return cv2.perspectiveTransform(np.float32([pts]), Hp)[0]


def poly_mask(shape, poly):
    m = np.zeros(shape[:2], np.uint8)
    cv2.fillPoly(m, [np.array(poly, np.int32)], 255)
    return m


def floor_grout(img, mask):
    """在 mask 内按地砖网格补画砖缝，再加一点细颗粒噪声，和原图地面质感对齐。"""
    h, w = mask.shape
    zone = (mask > 0) & (poly_mask(img.shape, FLOOR_ZONE) > 0)
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    uv = cv2.perspectiveTransform(np.dstack([xs, ys]).reshape(1, -1, 2), np.linalg.inv(FLOOR_H))
    u, v = uv.reshape(h, w, 2).transpose(2, 0, 1)
    gu = np.hypot(*np.gradient(u)[::-1])
    gv = np.hypot(*np.gradient(v)[::-1])
    du = np.abs(u - np.round(u)) / gu
    dv = np.abs(v - np.round(v)) / gv
    width = np.clip(0.0045 / np.minimum(gu, gv), 0.7, 1.4)
    line = np.maximum(np.exp(-(du / width) ** 2), np.exp(-(dv / width) ** 2))

    rng = np.random.default_rng(7)
    grain = cv2.GaussianBlur(rng.normal(0, 3.2, (h, w)).astype(np.float32), (0, 0), 0.6)

    out = img.astype(np.float32)
    shade = 1 - 0.11 * line
    soft = cv2.GaussianBlur(zone.astype(np.float32), (0, 0), 2)
    for c in range(3):
        target = out[..., c] * shade + grain
        out[..., c] = out[..., c] * (1 - soft) + target * soft
    return np.clip(out, 0, 255)


def warp_poster(poster, Hp, shape, s0, s1, t0, t1):
    """把海报贴到开口平面的 [s0,s1]×[t0,t1]（米）区域。t1<t0 时就是倒影。"""
    ph, pw = poster.shape[:2]
    src = np.float32([(0, ph), (pw, ph), (pw, 0), (0, 0)])
    dst = to_pixels(Hp, [(s0, t0), (s1, t0), (s1, t1), (s0, t1)])
    M = cv2.getPerspectiveTransform(src, dst)
    h, w = shape[:2]
    rgb = cv2.warpPerspective(poster, M, (w, h), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_REPLICATE)
    alpha = cv2.warpPerspective(np.full((ph, pw), 255, np.uint8), M, (w, h), flags=cv2.INTER_LINEAR)
    return rgb.astype(np.float32), alpha.astype(np.float32) / 255


def plane_gradient(Hp, shape, fn):
    """对开口平面上每个像素算 fn(s, t)，用来做光照和阴影。"""
    h, w = shape[:2]
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    st = cv2.perspectiveTransform(np.dstack([xs, ys]).reshape(1, -1, 2), np.linalg.inv(Hp))
    s, t = st.reshape(h, w, 2).transpose(2, 0, 1)
    return fn(s, t)


def main(venue_path, cleared_path, mask_path, poster_path, out_path):
    venue = cv2.imread(venue_path)
    cleared = cv2.imread(cleared_path)
    mask = cv2.imread(mask_path, 0)
    poster = cv2.imread(poster_path)

    img = floor_grout(cleared, mask)
    Hp = gap_homography()
    s0 = (GAP_W - TRUSS_W) / 2
    s1 = s0 + TRUSS_W

    # 画面在室内灯光下：略降饱和、提一点暗部、整体压暗
    hsv = cv2.cvtColor(poster, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] *= 0.85
    poster_lit = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)
    poster_lit = (poster_lit * 0.84 + 14).clip(0, 255).astype(np.uint8)

    # 地面倒影：海报以地面为镜，往下延伸，模糊并渐隐
    refl_rgb, refl_a = warp_poster(poster_lit, Hp, img.shape, s0, s1, 0, -TRUSS_H)
    fade = plane_gradient(Hp, img.shape, lambda s, t: np.clip(1 + t / 0.55, 0, 1) ** 2 * (t < 0))
    refl_a = cv2.GaussianBlur(refl_a * fade, (0, 0), 3) * 0.16
    refl_rgb = cv2.GaussianBlur(refl_rgb, (0, 0), 5)
    floor_only = (poly_mask(img.shape, FLOOR_ZONE) > 0).astype(np.float32)
    refl_a *= cv2.GaussianBlur(floor_only, (0, 0), 3)
    img = img * (1 - refl_a[..., None]) + refl_rgb * refl_a[..., None]

    # 行架底部和地面的接触阴影
    bottom = to_pixels(Hp, [(s0 - 0.05, 0), (s1 + 0.05, 0)])
    ao = np.zeros(img.shape[:2], np.float32)
    cv2.line(ao, tuple(map(int, bottom[0])), tuple(map(int, bottom[1])), 1.0, 5)
    ao = cv2.GaussianBlur(ao, (0, 0), 6) * floor_only
    img *= (1 - 0.35 * np.clip(ao * 2.2, 0, 1))[..., None]

    # 画面本体 + 光照：顶部靠横梁、底部贴地都略暗，右侧离灯近略亮
    rgb, alpha = warp_poster(poster_lit, Hp, img.shape, s0, s1, 0, TRUSS_H)
    light = plane_gradient(Hp, img.shape, lambda s, t: 1.0 - 0.07 * (t / TRUSS_H) ** 2 - 0.05 * np.exp(-t / 0.25)
                           + 0.03 * (s - s0) / TRUSS_W)
    rgb *= light[..., None]
    rgb = cv2.GaussianBlur(rgb, (0, 0), 0.45)

    # 行架方管：画面四周一圈细的银灰边
    frame = np.zeros(img.shape[:2], np.uint8)
    outer = to_pixels(Hp, [(s0, 0), (s1, 0), (s1, TRUSS_H), (s0, TRUSS_H)])
    inner = to_pixels(Hp, [(s0 + FRAME, FRAME), (s1 - FRAME, FRAME), (s1 - FRAME, TRUSS_H - FRAME),
                           (s0 + FRAME, TRUSS_H - FRAME)])
    cv2.fillPoly(frame, [outer.astype(np.int32)], 255)
    cv2.fillPoly(frame, [inner.astype(np.int32)], 0)
    frame_a = cv2.GaussianBlur(frame.astype(np.float32) / 255, (0, 0), 0.6)
    steel = np.array([92, 90, 88], np.float32)
    rgb = rgb * (1 - frame_a[..., None]) + steel * frame_a[..., None]

    a = alpha[..., None]
    img = img * (1 - a) + rgb * a

    # 沙发右端在行架前面，盖回去
    sofa = cv2.GaussianBlur(poly_mask(img.shape, LEFT_SOFA).astype(np.float32) / 255, (0, 0), 0.7)[..., None]
    img = img * (1 - sofa) + cleared.astype(np.float32) * sofa

    # 和照片统一颗粒
    rng = np.random.default_rng(3)
    img += (rng.normal(0, 1.6, img.shape[:2]).astype(np.float32) * alpha)[..., None]

    cv2.imwrite(out_path, np.clip(img, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 93])
    side = np.hstack([venue, np.clip(img, 0, 255).astype(np.uint8)])
    cv2.imwrite(out_path.replace(".jpg", "-compare.jpg"), cv2.resize(side, None, fx=0.5, fy=0.5,
                interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("wrote", out_path)


if __name__ == "__main__":
    main(*sys.argv[1:6])
