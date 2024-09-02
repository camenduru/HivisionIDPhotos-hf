import gradio as gr
import onnxruntime
from src.face_judgement_align import IDphotos_create
from hivisionai.hycv.vision import add_background
from src.layoutCreate import generate_layout_photo, generate_layout_image
import pathlib
import numpy as np
from image_utils import resize_image_to_kb
from data_utils import csv_to_size_list

# 获取尺寸列表
size_list_dict = csv_to_size_list("size_list_CN.csv")
print(size_list_dict)

color_list_dict = {
    "蓝色": (86, 140, 212),
    "白色": (255, 255, 255),
    "红色": (233, 51, 35),
}


# 设置Gradio examples
def set_example_image(example: list) -> dict:
    return gr.Image.update(value=example[0])


# 检测RGB是否超出范围，如果超出则约束到0～255之间
def range_check(value, min_value=0, max_value=255):
    value = int(value)
    if value <= min_value:
        value = min_value
    elif value > max_value:
        value = max_value
    return value


def idphoto_inference(
    input_image,
    mode_option,
    size_list_option,
    color_option,
    render_option,
    image_kb_options,
    custom_color_R,
    custom_color_G,
    custom_color_B,
    custom_size_height,
    custom_size_width,
    custom_image_kb,
    head_measure_ratio=0.2,
    head_height_ratio=0.45,
    top_distance_max=0.12,
    top_distance_min=0.10,
):

    idphoto_json = {
        "size_mode": mode_option,
        "color_mode": color_option,
        "render_mode": render_option,
        "image_kb_mode": image_kb_options,
    }

    # 如果尺寸模式选择的是尺寸列表
    if idphoto_json["size_mode"] == "尺寸列表":
        idphoto_json["size"] = size_list_dict[size_list_option]
    # 如果尺寸模式选择的是自定义尺寸
    elif idphoto_json["size_mode"] == "自定义尺寸":
        id_height = int(custom_size_height)
        id_width = int(custom_size_width)
        if (
            id_height < id_width
            or min(id_height, id_width) < 100
            or max(id_height, id_width) > 1800
        ):
            return {
                img_output_standard: gr.update(value=None),
                img_output_standard_hd: gr.update(value=None),
                notification: gr.update(
                    value="宽度应不大于长度；长宽不应小于100，大于1800", visible=True
                ),
            }
        idphoto_json["size"] = (id_height, id_width)
    else:
        idphoto_json["size"] = (None, None)

    # 如果颜色模式选择的是自定义底色
    if idphoto_json["color_mode"] == "自定义底色":
        idphoto_json["color_bgr"] = (
            range_check(custom_color_R),
            range_check(custom_color_G),
            range_check(custom_color_B),
        )
    else:
        idphoto_json["color_bgr"] = color_list_dict[color_option]

    # 如果输出KB大小选择的是自定义
    if idphoto_json["image_kb_mode"] == "自定义":
        idphoto_json["custom_image_kb"] = custom_image_kb
    else:
        idphoto_json["custom_image_kb"] = None

    # 生成证件照
    (
        result_image_hd,
        result_image_standard,
        typography_arr,
        typography_rotate,
        _,
        _,
        _,
        _,
        status,
    ) = IDphotos_create(
        input_image,
        mode=idphoto_json["size_mode"],
        size=idphoto_json["size"],
        head_measure_ratio=head_measure_ratio,
        head_height_ratio=head_height_ratio,
        align=False,
        beauty=False,
        fd68=None,
        human_sess=sess,
        IS_DEBUG=False,
        top_distance_max=top_distance_max,
        top_distance_min=top_distance_min,
    )

    # 如果检测到人脸数量不等于1
    if status == 0:
        result_messgae = {
            img_output_standard: gr.update(value=None),
            img_output_standard_hd: gr.update(value=None),
            notification: gr.update(value="人脸数量不等于1", visible=True),
        }

    # 如果检测到人脸数量等于1
    else:
        if idphoto_json["render_mode"] == "纯色":
            result_image_standard = np.uint8(
                add_background(result_image_standard, bgr=idphoto_json["color_bgr"])
            )
            result_image_hd = np.uint8(
                add_background(result_image_hd, bgr=idphoto_json["color_bgr"])
            )
        elif idphoto_json["render_mode"] == "上下渐变(白)":
            result_image_standard = np.uint8(
                add_background(
                    result_image_standard,
                    bgr=idphoto_json["color_bgr"],
                    mode="updown_gradient",
                )
            )
            result_image_hd = np.uint8(
                add_background(
                    result_image_hd,
                    bgr=idphoto_json["color_bgr"],
                    mode="updown_gradient",
                )
            )
        else:
            result_image_standard = np.uint8(
                add_background(
                    result_image_standard,
                    bgr=idphoto_json["color_bgr"],
                    mode="center_gradient",
                )
            )
            result_image_hd = np.uint8(
                add_background(
                    result_image_hd,
                    bgr=idphoto_json["color_bgr"],
                    mode="center_gradient",
                )
            )

        if idphoto_json["size_mode"] == "只换底":
            result_layout_image = gr.update(visible=False)
        else:
            typography_arr, typography_rotate = generate_layout_photo(
                input_height=idphoto_json["size"][0],
                input_width=idphoto_json["size"][1],
            )

            result_layout_image = generate_layout_image(
                result_image_standard,
                typography_arr,
                typography_rotate,
                height=idphoto_json["size"][0],
                width=idphoto_json["size"][1],
            )

        # 如果输出KB大小选择的是自定义
        if idphoto_json["custom_image_kb"]:
            # 将标准照大小调整至目标大小
            print("调整kb大小到", idphoto_json["custom_image_kb"], "kb")
            # 输出路径为一个根据时间戳+哈希值生成的随机文件名
            import time

            output_image_path = f"./output/{int(time.time())}.jpg"
            resize_image_to_kb(
                result_image_standard,
                output_image_path,
                idphoto_json["custom_image_kb"],
            )
        else:
            output_image_path = None

        if output_image_path:
            result_messgae = {
                img_output_standard: result_image_standard,
                img_output_standard_hd: result_image_hd,
                img_output_layout: result_layout_image,
                notification: gr.update(visible=False),
                file_download: gr.update(visible=True, value=output_image_path),
            }
        else:
            result_messgae = {
                img_output_standard: result_image_standard,
                img_output_standard_hd: result_image_hd,
                img_output_layout: result_layout_image,
                notification: gr.update(visible=False),
                file_download: gr.update(visible=False),
            }

    return result_messgae


if __name__ == "__main__":
    # 预加载ONNX模型
    HY_HUMAN_MATTING_WEIGHTS_PATH = "./hivision_modnet.onnx"
    sess = onnxruntime.InferenceSession(HY_HUMAN_MATTING_WEIGHTS_PATH)

    size_mode = ["尺寸列表", "只换底", "自定义尺寸"]
    size_list = list(size_list_dict.keys())
    colors = ["蓝色", "白色", "红色", "自定义底色"]
    render = ["纯色", "上下渐变(白)", "中心渐变(白)"]
    image_kb = ["不设置", "自定义"]

    title = "<h1 id='title'>HivisionIDPhotos</h1>"
    description = "<h3>😎9.2更新：新增照片大小KB调整</h3>"
    css = """
    h1#title, h3 {
      text-align: center;
    }
    """

    demo = gr.Blocks(css=css)

    with demo:
        gr.Markdown(title)
        gr.Markdown(description)
        with gr.Row():
            # ------------ 左半边UI ----------------
            with gr.Column():
                img_input = gr.Image().style(height=350)
                mode_options = gr.Radio(
                    choices=size_mode,
                    label="证件照尺寸选项",
                    value="尺寸列表",
                    elem_id="size",
                )
                # 预设尺寸下拉菜单
                with gr.Row(visible=True) as size_list_row:
                    size_list_options = gr.Dropdown(
                        choices=size_list,
                        label="预设尺寸",
                        value="一寸",
                        elem_id="size_list",
                    )

                with gr.Row(visible=False) as custom_size:
                    custom_size_height = gr.Number(
                        value=413, label="height", interactive=True
                    )
                    custom_size_wdith = gr.Number(
                        value=295, label="width", interactive=True
                    )

                # 左：背景色选项
                color_options = gr.Radio(
                    choices=colors, label="背景色", value="蓝色", elem_id="color"
                )

                # 左：如果选择「自定义底色」，显示RGB输入框
                with gr.Row(visible=False) as custom_color:
                    custom_color_R = gr.Number(value=0, label="R", interactive=True)
                    custom_color_G = gr.Number(value=0, label="G", interactive=True)
                    custom_color_B = gr.Number(value=0, label="B", interactive=True)

                # 左：渲染方式选项
                render_options = gr.Radio(
                    choices=render,
                    label="渲染方式",
                    value="纯色",
                    elem_id="render",
                )

                # 左：输出KB大小选项
                image_kb_options = gr.Radio(
                    choices=image_kb,
                    label="设置KB大小（结果在右边最底的组件下载）",
                    value="不设置",
                    elem_id="image_kb",
                )

                # 自定义KB大小, 滑动条，最小10KB，最大200KB
                with gr.Row(visible=False) as custom_image_kb:
                    custom_image_kb_size = gr.Slider(
                        minimum=10,
                        maximum=1000,
                        value=50,
                        label="KB大小",
                        interactive=True,
                    )

                img_but = gr.Button("开始制作")

                # 案例图片
                example_images = gr.Dataset(
                    components=[img_input],
                    samples=[
                        [path.as_posix()]
                        for path in sorted(pathlib.Path("images").rglob("*.jpg"))
                    ],
                )

            # ---------------- 右半边UI ----------------
            with gr.Column():
                notification = gr.Text(label="状态", visible=False)
                with gr.Row():
                    img_output_standard = gr.Image(label="标准照").style(height=350)
                    img_output_standard_hd = gr.Image(label="高清照").style(height=350)
                img_output_layout = gr.Image(label="六寸排版照").style(height=350)
                file_download = gr.File(label="下载调整KB大小后的照片", visible=False)

            # ---------------- 设置隐藏/显示组件 ----------------
            def change_color(colors):
                if colors == "自定义底色":
                    return {custom_color: gr.update(visible=True)}
                else:
                    return {custom_color: gr.update(visible=False)}

            def change_size_mode(size_option_item):
                if size_option_item == "自定义尺寸":
                    return {
                        custom_size: gr.update(visible=True),
                        size_list_row: gr.update(visible=False),
                    }
                elif size_option_item == "只换底":
                    return {
                        custom_size: gr.update(visible=False),
                        size_list_row: gr.update(visible=False),
                    }
                else:
                    return {
                        custom_size: gr.update(visible=False),
                        size_list_row: gr.update(visible=True),
                    }

            def change_image_kb(image_kb_option):
                if image_kb_option == "自定义":
                    return {custom_image_kb: gr.update(visible=True)}
                else:
                    return {custom_image_kb: gr.update(visible=False)}

        # ---------------- 绑定事件 ----------------
        color_options.input(
            change_color, inputs=[color_options], outputs=[custom_color]
        )

        mode_options.input(
            change_size_mode,
            inputs=[mode_options],
            outputs=[custom_size, size_list_row],
        )

        image_kb_options.input(
            change_image_kb, inputs=[image_kb_options], outputs=[custom_image_kb]
        )

        img_but.click(
            idphoto_inference,
            inputs=[
                img_input,
                mode_options,
                size_list_options,
                color_options,
                render_options,
                image_kb_options,
                custom_color_R,
                custom_color_G,
                custom_color_B,
                custom_size_height,
                custom_size_wdith,
                custom_image_kb_size,
            ],
            outputs=[
                img_output_standard,
                img_output_standard_hd,
                img_output_layout,
                notification,
                file_download,
            ],
        )

        example_images.click(
            fn=set_example_image, inputs=[example_images], outputs=[img_input]
        )

    demo.launch()
