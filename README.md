# EECE-4811-Hw4

Q1. 

**Job** |	**Response** | 	**Turnaround**

A 		|	0 |	200

B |	200 |	400

C |	400 |	600

**Avg** |	200 |	400

Q2. 

**Job |	Response |	Turnaround**

A (100) |	0 |	100

B (200) |	100 |	300

C (300) |	300 |	600

**Avg** |	133.33 |	333.33

Q3. 

**Policy |	Avg response (200×3) |	Avg turnaround (200×3) |	Avg response (100/200/300) |	Avg turnaround (100/200/300)**

FIFO |	200 |	400 |	133.33 |	333.33

SJF |	200 |	400 |	133.33 |	333.33

RR (q=1) |	1 |	599 |	1 |	465.67

Q4. 

SJF matches FIFO whenever FIFO’s order is already shortest-job-first. Which happens in the following two cases:

When all jobs have the same length and the jobs arrive in non-decreasing order of length.

Q5. 

Under SJF, each earlier job runs to completion, so a job waits for the full length of every earlier job.

Under RR, each earlier job runs for min(q, its length) before the next one starts.

So the two are equal when:

The quantum is at least as long as every job except the last one to start and RR’s order matches SJF’s order. This means equal-length jobs, or jobs that arrive sorted shortest-first.


