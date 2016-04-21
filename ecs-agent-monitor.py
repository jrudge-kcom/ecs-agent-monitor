import boto3

def main(event, context):
  if not u'cluster' in context:
    raise Exception(
      "Key u'cluster' not found in the context object! Which cluster should I scan?!"
    )

  ecs_client = boto3.client("ecs")

  resp = ecs_client.list_container_instances(
    cluster=context[u'cluster']
  )

  instances = resp[u'containerInstanceArns']

  try:
    nxt_tok = resp[u'nextToken']

    while True:
      resp = ecs_client.list_container_instances(
        cluster=context[u'cluster'],
        nextToken=nxt_tok
      )

      instances += resp[u'containerInstanceArns']
      nxt_tok = resp[u'nextToken']
  except KeyError:
    pass

  resp = ecs_client.describe_container_instances(
    cluster=context[u'cluster'],
    containerInstances=instances
  )

  ec2 = boto3.resource("ec2")
  autoscale_client = boto3.client("autoscaling")

  terminated = []

  for inst in resp[u'containerInstances']:
    if not inst[u'agentConnected']:
      I = ec2.Instance(id=inst[u'ec2InstanceId'])

      autoscalegroup = [x[u'Value'] for x in I.tags if x[u'Key'] == u'aws:autoscaling:groupName'][0]

      # Danger! Detaching Instance from autoscaling group
      autoscale_client.detach_instances(
        InstanceIds=[I.id],
        AutoScalingGroupName=autoscalegroup,
        ShouldDecrementDesiredCapacity=False
      )

      # Danger! Terminating Instance
      I.terminate()

      terminated.append(I.id)
      print "Detaching and Terminating: %s in autoscale group %s"
        % (I.id, autoscalegroup)

  # If instances were terminated, send summary to an SNS topic (if we have the ARN)
  if len(terminated) != 0 and u'snsLogArn' in context:
    sns = boto3.resource("sns")
    topic = sns.Topic(context[u'snsLogArn'])

    topic.publish(
      Subject="AWS Lambda: ECS-Agent-Monitor",
      Message=\
"""
The ecs-agent-monitor function running in AWS Lambda has detected %i EC2
Instances whose ECS `ecs-agent' process has died.

The following Instances were detached from their autoscaling groups and
terminated:

%s
""" % (len(terminated), "\n".join(terminated))
    )