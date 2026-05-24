# canonical_witness_matrix_median

> 状态：`schema_insufficient`

## 生成中止原因

new_schema中core_constraints的canonical_ordering强制输出每行升序排列，与valid_permuted_rows结合导致每一行的升序排列唯一且中位数固定，无法实现objective中的最大化最小中位数和字典序选择，算法自由于此丧失，无法构造合理题目。

## 反馈

无
