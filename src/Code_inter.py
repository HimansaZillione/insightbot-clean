import matplotlib.pyplot as plt

# Data for the pie chart
specializations = [
    "Information Technology",
    "Information Systems Engineering",
    "Software Engineering",
    "Interactive Media",
    "Computer Systems & Network Engineering",
    "Cyber Security",
    "Data Science"
]

graduates = [107, 17, 48, 13, 14, 23, 15]

# Creating the pie chart
plt.figure(figsize=(8, 8))
plt.pie(graduates, labels=specializations, autopct='%1.1f%%', startangle=140, colors=plt.cm.Paired.colors)

# Title of the chart
plt.title("IT Graduates by Specialization (2022)")

# Displaying the chart
plt.show()