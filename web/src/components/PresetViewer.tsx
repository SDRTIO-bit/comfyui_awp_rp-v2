import { useEffect, useState } from "react";
import { Button, Collapse, Modal, Select, Typography } from "antd";
import { FolderOpenOutlined } from "@ant-design/icons";
import { getWriterPreset, listWriterPresets } from "../api/client";

const { Paragraph, Text } = Typography;

export default function PresetViewer() {
  const [presets, setPresets] = useState<string[]>([]);
  const [selected, setSelected] = useState("");
  const [content, setContent] = useState("");
  const [path, setPath] = useState("");

  useEffect(() => {
    listWriterPresets()
      .then(setPresets)
      .catch(() => setPresets([]));
  }, []);

  useEffect(() => {
    if (!selected) {
      setContent("");
      setPath("");
      return;
    }
    getWriterPreset(selected)
      .then((preset) => {
        setContent(preset.content);
        setPath(preset.path);
      })
      .catch(() => {
        setContent("");
        setPath("");
      });
  }, [selected]);

  return (
    <Collapse
      ghost
      items={[
        {
          key: "writer-presets",
          label: "写作预设",
          children: (
            <>
              <Select
                options={presets.map((preset) => ({ value: preset, label: preset }))}
                placeholder="选择预设"
                style={{ width: "100%" }}
                value={selected || undefined}
                onChange={setSelected}
              />
              {selected && (
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    路径：{path}
                  </Text>
                  <Paragraph
                    style={{
                      marginTop: 8,
                      whiteSpace: "pre-wrap",
                      maxHeight: 220,
                      overflow: "auto",
                      background: "#fff",
                      border: "1px solid #f0f0f0",
                      padding: 8,
                      borderRadius: 6,
                    }}
                  >
                    {content}
                  </Paragraph>
                  <Button
                    size="small"
                    icon={<FolderOpenOutlined />}
                    onClick={() => {
                      Modal.info({
                        title: "编辑预设",
                        content: `请从本机文件系统打开：${path}`,
                      });
                    }}
                  >
                    定位文件
                  </Button>
                </div>
              )}
            </>
          ),
        },
      ]}
    />
  );
}
