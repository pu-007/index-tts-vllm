#!/bin/bash
# 脚本名称: sync_upstream.sh
# 作用: 将原作者仓库 (origin) 的最新更新同步到当前分支，并推送到你的个人远端 (pu-007)。

set -e # 遇到错误时立即退出

ORIGINAL_REMOTE="origin"
MY_REMOTE="pu-007"
BRANCH="master" # 如果原作者默认分支不是 master 而是 main，可在此处修改

echo "==== 1. 获取原仓库 ($ORIGINAL_REMOTE) 的最新代码 ===="
git fetch $ORIGINAL_REMOTE

echo "==== 2. 切换到本地 $BRANCH 分支 ===="
git checkout $BRANCH

echo "==== 3. 将 $ORIGINAL_REMOTE/$BRANCH 的更改合并到本地 ===="
# 尝试合并原作者的最新代码。
# 也可以使用 rebase 来合并，以保持 commit 提交历史的线性整洁: git rebase $ORIGINAL_REMOTE/$BRANCH
git merge $ORIGINAL_REMOTE/$BRANCH -m "Merge upstream changes from $ORIGINAL_REMOTE/$BRANCH"

echo "==== 4. 将同步后的代码推送到你的远端仓库 ($MY_REMOTE) ===="
git push $MY_REMOTE $BRANCH

echo "==== ✅ 同步完成！ ===="
