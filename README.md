### 0) 如果專案有用到 conda 的話，這裡提供 conda 小抄

```bash
conda env create -f environment.yaml
conda activate dayXX_XXX

# 停用環境
conda deactivate

# 查看所有環境
conda env list

# 刪除環境（⚠️ 慎用）
conda env remove -n dayXX_XXX

# 更新環境（當 environment.yml 有修改時）
conda env update -f environment.yml --prune
```
