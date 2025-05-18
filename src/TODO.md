


- check baseline removal of Si 

- do cosine only for the interpolation range of Ne spectrum 

- compare against the peaks - or compare against the entire PST spectrum from NIST  (after convolution )

- quality factor of spectra 

- another metric for comparison 


- check 0801 and 01001 APAP 

- unit tests 



def test_pipeline_runs():
    import subprocess
    result = subprocess.run(["ploomber", "build"], check=True)
