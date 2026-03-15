E. Dead Ends

Life in Bertown has become hard. The city has too many roads and the government spends too much to maintain them. There are n junctions and m two way roads, at which one can get from each junction to any other one. The mayor wants to close some roads so that the number of roads left totaled to n - 1 roads and it were still possible to get from each junction to any other one. Besides, the mayor is concerned with the number of dead ends which are the junctions from which only one road goes. There shouldn't be too many or too few junctions. Having discussed the problem, the mayor and his assistants decided that after the roads are closed, the road map should contain exactly k dead ends. Your task is to count the number of different ways of closing the roads at which the following conditions are met:

Two ways are considered different if there is a road that is closed in the first way, and is open in the second one.

Input
The first line contains three integers n, m and k (3 ≤ n ≤ 10, n - 1 ≤ m ≤ n ·(n - 1) / 2, 2 ≤ k ≤ n - 1) which represent the number of junctions, roads and dead ends correspondingly. Then follow m lines each containing two different integers v 1 and v 2 (1 ≤ v 1, v 2 ≤ n, v 1 ≠ v 2) which represent the number of junctions connected by another road. There can be no more than one road between every pair of junctions. The junctions are numbered with integers from 1 to n. It is guaranteed that it is possible to get from each junction to any other one along the original roads.

Output
Print a single number — the required number of ways.

Constraints
time limit per test 5 seconds
memory limit per test 256 megabytes