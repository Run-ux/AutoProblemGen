D. Grocer's Problem

Yesterday was a fair in a supermarket's grocery section. There were n jars with spices on the fair. Before the event the jars were numbered from 1 to n from the left to the right. After the event the jars were moved and the grocer had to sort them by the increasing of the numbers.

The grocer has a special machine at his disposal. The machine can take any 5 or less jars and rearrange them in the way the grocer wants. Note that the jars do not have to stand consecutively. For example, from the permutation 2, 6, 5, 4, 3, 1 one can get permutation 1, 2, 3, 4, 5, 6, if pick the jars on the positions 1, 2, 3, 5 and 6.

Which minimum number of such operations is needed to arrange all the jars in the order of their numbers' increasing?

Input
The first line contains an integer n (1 ≤ n ≤ 10 5). The second line contains n space-separated integers a i (1 ≤ a i ≤ n) — the i -th number represents the number of a jar that occupies the i -th position. It is guaranteed that all the numbers are distinct.

Output
Print on the first line the least number of operations needed to rearrange all the jars in the order of the numbers' increasing. Then print the description of all actions in the following format. On the first line of the description of one action indicate the number of jars that need to be taken (k), on the second line indicate from which positions the jars need to be taken (b 1, b 2, ..., b k), on the third line indicate the jar's new order (c 1, c 2, ..., c k). After the operation is fulfilled the jar from position b i will occupy the position c i. The set (c 1, c 2, ..., c k) should be the rearrangement of the set (b 1, b 2, ..., b k). If there are multiple solutions, output any.

Constraints
time limit per test 2 seconds
memory limit per test 256 megabytes